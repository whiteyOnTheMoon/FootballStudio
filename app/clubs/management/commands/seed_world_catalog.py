"""Idempotent, zero-network seed of all configured confederations and associations.

Never deletes manual clubs, league records or previous jobs. Run after migrations.
Only 2026/27, source-attributed participant lists in the versioned snapshot
receive coverage_status=snapshot; reference-only leagues are not falsely verified.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app.clubs.models import Club, Confederation, Country, League

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def read_data(filename):
    path = DATA_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def validate_data(index, snapshots):
    confeds = {x["code"] for x in index["confederations"]}
    if confeds != {"UEFA", "AFC", "CAF", "CONCACAF", "CONMEBOL", "OFC"}:
        raise CommandError("Unexpected set of football confederations.")
    uefa = [x for x in index["associations"] if x["confederation"] == "UEFA"]
    if len(uefa) != 55:
        raise CommandError(f"Expected all 55 UEFA associations, found {len(uefa)}")
    keys = set()
    for association in index["associations"]:
        key = association["code"]
        if key in keys:
            raise CommandError(f"Duplicate association code: {key}")
        keys.add(key)
        if association["confederation"] not in confeds:
            raise CommandError(f"Unknown confederation: {key}")
        tiers = {row["tier"] for row in association["leagues"]}
        if not {1, 2}.issubset(tiers) and not (
            association["exception"] or association["confederation"] != "UEFA"
        ):
            raise CommandError(f"Unexplained missing UEFA tier: {key}")
    for item in snapshots["leagues"]:
        if item["association"] not in keys or len(item["teams"]) < 10:
            raise CommandError("Invalid snapshot: unknown association/too few teams")
        allowed_sources = (
            "https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/",
            "https://raw.githubusercontent.com/openfootball/europe/master/",
            "https://raw.githubusercontent.com/openfootball/austria/master/2026-27/",
            "https://raw.githubusercontent.com/openfootball/deutschland/master/openliga/2026-27_",
        )
        if not item.get("source_url", "").startswith(allowed_sources):
            raise CommandError("Untrusted snapshot source.")
        if item.get("provider") == "openligadb-snapshot" and "ODbL" not in item.get("license", ""):
            raise CommandError("Missing OpenLigaDB ODbL attribution.")
        if item.get("provider") not in ("openfootball", "openligadb-snapshot"):
            raise CommandError("Unsupported snapshot provider.")
        if len({x.casefold() for x in item["teams"]}) != len(item["teams"]):
            raise CommandError("Duplicate club in versioned source snapshot.")


class Command(BaseCommand):
    help = "Seed offline world confederations, UEFA 55 and versioned club rosters without APIs."

    def add_arguments(self, parser):
        parser.add_argument("--without-teams", action="store_true",
                            help="Seed only associations and league references, not teams.")

    def handle(self, *args, **options):
        index = read_data("world_catalog.json")
        snapshots = read_data("teams-2026-27.json")
        validate_data(index, snapshots)
        club_count = 0
        with transaction.atomic():
            confeds = {}
            for row in index["confederations"]:
                obj, _ = Confederation.objects.update_or_create(
                    code=row["code"], defaults={"name": row["name"]}
                )
                confeds[row["code"]] = obj
            countries = {}
            for row in index["associations"]:
                country, _ = Country.objects.update_or_create(
                    code=row["code"],
                    defaults={
                        "name": row["name"],
                        "confederation": confeds[row["confederation"]],
                        "is_active": True,
                    },
                )
                countries[row["code"]] = country
                for league_row in row["leagues"]:
                    league = League.objects.filter(
                        country=country, name__iexact=league_row["name"],
                    ).first()
                    if league is None:
                        League.objects.create(
                            country=country,
                            name=league_row["name"], tier=league_row["tier"],
                            provider="offline-reference",
                            coverage_status="reference",
                        )
                    elif league.tier != league_row["tier"]:
                        # Do not silently change manually edited league tiers.
                        self.stderr.write(
                            f"Review tier for {row['code']}: {league.name}"
                        )

            if not options["without_teams"]:
                for row in snapshots["leagues"]:
                    country = countries[row["association"]]
                    league = League.objects.filter(
                        country=country, tier=row["tier"],
                        is_active=True,
                    ).order_by("pk").first()
                    if league is None:
                        raise CommandError(
                            f"Missing catalog league for snapshot: {country.code}"
                        )
                    for name in row["teams"]:
                        existing = Club.objects.filter(
                            league=league, name__iexact=name
                        ).first()
                        if existing is None:
                            Club.objects.create(
                                league=league, name=name,
                                provider=row["provider"],
                                provider_id=hashlib.sha256(
                                    name.casefold().encode("utf-8")
                                ).hexdigest()[:32],
                                is_manual=False, is_active=True,
                            )
                            club_count += 1
                        elif not existing.is_manual and not existing.is_active:
                            Club.objects.filter(pk=existing.pk).update(is_active=True)
                    League.objects.filter(pk=league.pk).update(
                        coverage_status="snapshot",
                        provider=row["provider"],
                        source_url=row["source_url"],
                        catalog_season=row["season"],
                    )
        self.stdout.write(self.style.SUCCESS(
            f"Offline catalog imported: {len(confeds)} confederations, "
            f"{len(countries)} associations, {club_count} new club records."
        ))
