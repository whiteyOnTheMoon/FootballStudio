#!/usr/bin/env python3
"""Opt-in live M1 catalog smoke check against keyless public endpoints.

Run only in ephemeral test environments. This is NOT a fixture test,
a production import, or a guarantee that provider coverage stays stable.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.config.settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from app.clubs.catalog import (  # noqa: E402
    CatalogUnavailable, discover_countries, season_label, season_start, sync_league_teams,
)
from app.clubs.models import Club  # noqa: E402


def main():
    call_command("migrate", interactive=False, verbosity=0)
    year = season_start()
    countries, errors = discover_countries(year)
    print("Season:", season_label(year))
    print("Detected countries:", [(x.code, x.name) for x in countries])
    print("Source warnings:", errors)
    if {x.code for x in countries} != {"GB", "DE"}:
        raise RuntimeError(
            "Expected current-season top two leagues from both England and Germany. "
            "Check API availability and do not claim unverified coverage."
        )
    for country in countries:
        first_two = list(
            country.leagues.filter(
                is_active=True, catalog_season=season_label(year), tier__in=(1, 2)
            ).order_by("tier")
        )
        if len(first_two) != 2:
            raise RuntimeError(f"{country.code}: cannot confirm top two leagues")
        for league in first_two:
            try:
                sync_league_teams(league, year)
            except CatalogUnavailable as exc:
                raise RuntimeError(
                    f"{country.code}: failed to load {league.provider_id} teams"
                ) from exc
            count = Club.objects.filter(league=league, is_active=True).count()
            print(f"{country.code} tier {league.tier}: {league.name}, {count} clubs")
            if count < 10:
                raise RuntimeError(
                    f"{country.code} tier {league.tier}: truncated or missing team listing"
                )
    print("Live catalog smoke passed for two supported countries and two leagues each.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not print HTTP credentials or any sensitive response body.
        print(f"Live catalog check failed: {error}", file=sys.stderr)
        raise SystemExit(1)
