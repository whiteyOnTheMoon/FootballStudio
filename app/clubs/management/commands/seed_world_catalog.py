"""Idempotent, zero-network seed of all configured confederations and associations.

Never deletes manual clubs, league records or previous jobs. Run after migrations.
Only source-attributed, dated participant lists receive coverage_status=snapshot.
Older seasons remain selectable with visible season warnings; missing leagues
and parallel league groups are not silently invented or conflated.
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
    expected_members = {
        "UEFA": 55, "CAF": 54, "AFC": 46,
        "CONCACAF": 35, "CONMEBOL": 10, "OFC": 11,
    }
    actual_members = {
        code: sum(row["confederation"] == code for row in index["associations"])
        for code in expected_members
    }
    if actual_members != expected_members:
        raise CommandError(
            f"Invalid FIFA membership directory: {actual_members}; expected {expected_members}"
        )
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
    lookup = {row["code"]: row for row in index["associations"]}
    seen_league_rosters = set()
    for item in snapshots["leagues"]:
        if item["association"] not in keys or len(item["teams"]) < 4:
            raise CommandError("Invalid snapshot: unknown association/too few named teams")
        league_matches = [
            entry for entry in lookup[item["association"]]["leagues"]
            if entry["tier"] == item["tier"]
            and (
                not item.get("league")
                or entry["name"].casefold() == item["league"].casefold()
            )
        ]
        if len(league_matches) != 1:
            raise CommandError(
                f"Ambiguous/missing league in {item['association']} at tier {item['tier']}: "
                f"{item.get('league', '(unspecified)')}"
            )
        roster_key = (item["association"], league_matches[0]["name"].casefold())
        if roster_key in seen_league_rosters:
            raise CommandError("Duplicate league snapshot across offline packages.")
        seen_league_rosters.add(roster_key)
        allowed_sources = (
            "https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/",
            "https://raw.githubusercontent.com/openfootball/europe/master/",
            "https://raw.githubusercontent.com/openfootball/world/master/",
            "https://raw.githubusercontent.com/openfootball/south-america/master/",
            "https://raw.githubusercontent.com/openfootball/austria/master/2026-27/",
            "https://raw.githubusercontent.com/openfootball/austria/master/2025-26/",
            "https://raw.githubusercontent.com/openfootball/deutschland/master/openliga/2026-27_",
            "https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/",
            "https://raw.githubusercontent.com/openfootball/football.json/master/2025/",
            "https://raw.githubusercontent.com/openfootball/football.json/master/2026/",
            "https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/",
            "https://rfef.es/es/noticias/aprobados-los-grupos-de-primera-federacion-para-la-temporada-202627",
            "https://www.fff.fr/article/17022-le-calendrier-2026-2027-est-servi.html",
            "https://ettanfotboll.se/seriesammansattning-for-ettan-2026/",
            "https://www.jleague.jp/en/j3/standings/2026-27/",
            "https://www.frf.ro/recomandate/joi-20-august-tragerea-la-sorti-pentru-programul-superscore-liga-3-editia-2026-2027/",
            "https://www.tff.org/Default.aspx?pageID=976&grupID=",
            "https://www.national-football-teams.com/de/leagues/66/2026_2/Finland.html",
            "https://www.national-football-teams.com/de/leagues/85/2026_2/Iceland.html",
        )
        if not item.get("source_url", "").startswith(allowed_sources):
            raise CommandError("Untrusted snapshot source.")
        if item.get("provider") == "openligadb-snapshot" and "ODbL" not in item.get("license", ""):
            raise CommandError("Missing OpenLigaDB ODbL attribution.")
        if item.get("provider") not in ("openfootball", "openligadb-snapshot", "official-roster"):
            raise CommandError("Unsupported snapshot provider.")
        if item.get("provider") == "official-roster" and "attribution" not in item.get("license", "").lower():
            raise CommandError("Official-roster source attribution is missing.")
        if not item.get("season") or not item.get("license"):
            raise CommandError("Snapshot season and license statement are mandatory.")
        if item.get("coverage", "snapshot") not in {"snapshot", "partial"}:
            raise CommandError("Unknown snapshot coverage status.")
        if item.get("coverage") == "partial":
            if not item.get("coverage_note") or not item.get("expected_team_count"):
                raise CommandError("Partial rosters require documented gaps and expected count.")
            if item["expected_team_count"] <= len(item["teams"]):
                raise CommandError("Partial roster must be strictly smaller than reported field.")
        if any(not isinstance(n, str) or not n.strip() or n != n.strip() for n in item["teams"]):
            raise CommandError("Snapshot contains an invalid club name.")
        if len({x.casefold() for x in item["teams"]}) != len(item["teams"]):
            raise CommandError("Duplicate club in versioned source snapshot.")


class Command(BaseCommand):
    help = "Seed FIFA 211 member associations and versioned league/club data, offline."

    def add_arguments(self, parser):
        parser.add_argument("--without-teams", action="store_true",
                            help="Seed only associations and league references, not teams.")

    def handle(self, *args, **options):
        index = read_data("world_catalog.json")
        extension = read_data("fifa_member_associations_2026.json")
        index["associations"].extend(extension["associations"])
        snapshots = read_data("teams-2026-27.json")
        snapshots["leagues"].extend(read_data("teams-additional.json")["leagues"])
        snapshots["leagues"].extend(read_data("teams-verified-2026.json")["leagues"])
        # Reviewed, versioned packages. Never fetch remote data during selection
        # or seeding. Reorder only after checking overlapping league snapshots.
        for filename in (
            "teams-europe-history-a.json",
            "teams-europe-history-b.json",
            "teams-europe-history-c.json",
            "teams-europe-history-d.json",
            "teams-europe-history-e.json",
            "teams-world-africa.json",
            "teams-world-other.json",
            "teams-world-recovered.json",
            "teams-third-tiers-2026.json",
        ):
            snapshots["leagues"].extend(read_data(filename)["leagues"])
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
                            source_url=league_row.get("source_url", ""),
                        )
                    elif league.tier != league_row["tier"]:
                        # Do not silently change manually edited league tiers.
                        self.stderr.write(
                            f"Review tier for {row['code']}: {league.name}"
                        )

            if not options["without_teams"]:
                for row in snapshots["leagues"]:
                    country = countries[row["association"]]
                    candidates = League.objects.filter(
                        country=country, tier=row["tier"], is_active=True,
                    )
                    if row.get("league"):
                        candidates = candidates.filter(name__iexact=row["league"])
                    matches = list(candidates[:2])
                    if len(matches) != 1:
                        raise CommandError(
                            f"Ambiguous/missing catalog league for {country.code} "
                            f"tier {row['tier']} ({row.get('league', 'unspecified')})"
                        )
                    league = matches[0]
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
                        coverage_status=row.get("coverage", "snapshot"),
                        provider=row["provider"],
                        source_url=row["source_url"],
                        catalog_season=row["season"],
                    )
        self.stdout.write(self.style.SUCCESS(
            f"Offline catalog imported: {len(confeds)} confederations, "
            f"{len(countries)} associations, {club_count} new club records."
        ))
