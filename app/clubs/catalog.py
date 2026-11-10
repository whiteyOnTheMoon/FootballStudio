"""Keyless public football catalog adapters for the FIRST M1 prototype.

Sources:
- openfootball/football.json (CC0, current season fixture lists)
- OpenLigaDB (ODbL, current German league team lists)
Never search teams in a trimmed free-tier API or hardcode club memberships.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import Club, Country, League

OPENFOOTBALL_INDEX = (
    "https://api.github.com/repos/openfootball/football.json/contents/"
)
OPENFOOTBALL_RAW = (
    "https://raw.githubusercontent.com/openfootball/football.json/master/"
)
OPENLIGADB = "https://api.openligadb.de/"
PROVIDER_TIMEOUT = 7
MAX_JSON_BYTES = 2_000_000
DISCOVERY_CACHE_SECONDS = 6 * 60 * 60
TEAM_CACHE_SECONDS = 12 * 60 * 60

# Country and league *identifiers* are supported-provider configuration.
# The actual existence of a league and all its clubs come from live sources.
# 'GB' is the ISO-3166 code for the UK; the listed leagues are English.
CATALOG = {
    "GB": {
        "name": "England (UK)",
        "provider": "openfootball",
        "leagues": (
            ("en.1", "Premier League", 1),
            ("en.2", "Championship", 2),
            ("en.3", "League One", 3),
        ),
    },
    "DE": {
        "name": "Deutschland",
        "provider": "openligadb",
        "leagues": (
            ("bl1", "Bundesliga", 1),
            ("bl2", "2. Bundesliga", 2),
            ("bl3", "3. Liga", 3),
        ),
    },
}


class CatalogUnavailable(Exception):
    """The public data source is unreachable, incomplete, or malformed."""


@dataclass(frozen=True)
class TeamRecord:
    name: str
    external_id: str


def season_start(today: date | None = None) -> int:
    today = today or timezone.localdate()
    return today.year if today.month >= 7 else today.year - 1


def season_label(year: int) -> str:
    return f"{year}-{(year + 1) % 100:02d}"


def fetch_json(url: str):
    """Read only fixed, trusted HTTPS hosts; cap body size and timeouts."""
    if not (
        url.startswith(OPENFOOTBALL_INDEX)
        or url.startswith(OPENFOOTBALL_RAW)
        or url.startswith(OPENLIGADB)
    ):
        raise CatalogUnavailable("Unsupported catalog URL.")
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "FootballStudio/0.1 (https://github.com/whiteyOnTheMoon/FootballStudio)",
        },
    )
    try:
        with urlopen(request, timeout=PROVIDER_TIMEOUT) as response:
            payload = response.read(MAX_JSON_BYTES + 1)
            if len(payload) > MAX_JSON_BYTES:
                raise CatalogUnavailable("Catalog response is too large.")
        return json.loads(payload.decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, UnicodeError, ValueError, OSError) as exc:
        # Never expose request headers or internal Python exceptions in responses.
        raise CatalogUnavailable("The public catalog is temporarily unavailable.") from exc


def _available_league_codes(provider: str, year: int) -> set[str]:
    if provider == "openfootball":
        listing = fetch_json(f"{OPENFOOTBALL_INDEX}{season_label(year)}")
        if not isinstance(listing, list):
            raise CatalogUnavailable("The OpenFootball league index is incomplete.")
        return {
            item["name"][:-5]
            for item in listing
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and item["name"].endswith(".json")
            and item.get("size", 0) > 0
        }
    if provider == "openligadb":
        listing = fetch_json(f"{OPENLIGADB}getavailableleagues/{year}")
        if not isinstance(listing, list):
            raise CatalogUnavailable("The OpenLigaDB league index is incomplete.")
        return {
            item["leagueShortcut"].strip().lower()
            for item in listing
            if isinstance(item, dict)
            and isinstance(item.get("leagueShortcut"), str)
        }
    raise CatalogUnavailable("Unknown catalog provider.")


def _store_available_leagues(country_code: str, available: set[str], year: int):
    descriptor = CATALOG[country_code]
    current = [
        (code, name, tier)
        for code, name, tier in descriptor["leagues"]
        if code in available
    ]
    # Never advertise a country unless BOTH top divisions are present.
    if not {1, 2}.issubset({tier for _, _, tier in current}):
        return
    with transaction.atomic():
        country, _ = Country.objects.get_or_create(
            code=country_code, defaults={"name": descriptor["name"]}
        )
        if country.name != descriptor["name"] or not country.is_active:
            Country.objects.filter(pk=country.pk).update(
                name=descriptor["name"], is_active=True
            )
        for code, name, tier in current:
            league = League.objects.filter(
                country=country, name__iexact=name
            ).first()
            if league is None:
                League.objects.create(
                    country=country, name=name, tier=tier,
                    provider=descriptor["provider"], provider_id=code,
                    catalog_season=season_label(year),
                )
            else:
                League.objects.filter(pk=league.pk).update(
                    tier=tier, provider=descriptor["provider"],
                    provider_id=code, catalog_season=season_label(year),
                    is_active=True,
                )


def discover_countries(year: int | None = None) -> tuple[list[Country], list[str]]:
    """Return only countries with at least two current supported tiers."""
    year = year or season_start()
    errors = []
    for code, info in CATALOG.items():
        key = f"footballstudio:discovery:{year}:{info['provider']}"
        if cache.get(key):
            continue
        try:
            available = _available_league_codes(info["provider"], year)
            _store_available_leagues(code, available, year)
            # Cache even if this source has only tier one, to avoid hammering.
            cache.set(key, True, DISCOVERY_CACHE_SECONDS)
        except CatalogUnavailable:
            errors.append(f"{info['name']}: data provider unavailable.")
    countries = []
    for country in Country.objects.filter(code__in=CATALOG, is_active=True).order_by("name"):
        tiers = set(
            country.leagues.filter(
                is_active=True, catalog_season=season_label(year)
            ).values_list("tier", flat=True)
        )
        if {1, 2}.issubset(tiers):
            countries.append(country)
    return countries, errors


def teams_for_league(league: League, year: int) -> list[TeamRecord]:
    descriptor = CATALOG.get(league.country.code)
    if not descriptor or (
        descriptor["provider"] != league.provider
        or league.provider_id not in {item[0] for item in descriptor["leagues"]}
        or league.catalog_season != season_label(year)
    ):
        raise CatalogUnavailable("This league has no available current-season catalog.")
    if league.provider == "openfootball":
        path = f"{season_label(year)}/{league.provider_id}.json"
        payload = fetch_json(OPENFOOTBALL_RAW + path)
        if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list):
            raise CatalogUnavailable("No valid fixture listing was returned.")
        names = {
            name.strip()
            for match in payload["matches"]
            if isinstance(match, dict)
            for name in (match.get("team1"), match.get("team2"))
            if isinstance(name, str) and 1 < len(name.strip()) <= 160
        }
        records = [
            TeamRecord(
                name=name,
                external_id=hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()[:32],
            )
            for name in sorted(names, key=str.casefold)
        ]
    elif league.provider == "openligadb":
        payload = fetch_json(
            f"{OPENLIGADB}getavailableteams/{league.provider_id}/{year}"
        )
        if not isinstance(payload, list):
            raise CatalogUnavailable("No valid team listing was returned.")
        records = [
            TeamRecord(name=team["teamName"].strip(), external_id=str(team["teamId"]))
            for team in payload
            if isinstance(team, dict)
            and isinstance(team.get("teamName"), str)
            and 1 < len(team["teamName"].strip()) <= 160
            and isinstance(team.get("teamId"), int)
        ]
    else:
        raise CatalogUnavailable("Unknown catalog provider.")
    if len({item.name.casefold() for item in records}) < 10:
        raise CatalogUnavailable(
            "This season has too few verified teams in the free data source."
        )
    deduplicated = {item.name.casefold(): item for item in records}
    return sorted(deduplicated.values(), key=lambda item: item.name.casefold())


def sync_league_teams(league: League, year: int | None = None) -> bool:
    """Import current-season clubs; return True if a network sync was needed.

    Successful imports retain manual clubs, deactivate obsolete *provider*
    records only, and preserve the last successful result on provider failures.
    """
    year = year or season_start()
    now = timezone.now()
    if (
        league.last_synced_at
        and league.catalog_season == season_label(year)
        and now - league.last_synced_at < timedelta(seconds=TEAM_CACHE_SECONDS)
        and league.clubs.filter(is_active=True).exists()
    ):
        return False
    teams = teams_for_league(league, year)
    seen = set()
    with transaction.atomic():
        for team in teams:
            existing = Club.objects.filter(
                league=league, name__iexact=team.name
            ).first()
            if existing is None:
                existing = Club.objects.create(
                    league=league,
                    name=team.name,
                    provider=league.provider,
                    provider_id=team.external_id,
                    is_manual=False,
                )
            elif not existing.is_manual:
                Club.objects.filter(pk=existing.pk).update(
                    name=team.name, provider=league.provider,
                    provider_id=team.external_id, is_active=True,
                )
            seen.add(existing.pk)
        # Manual entries belong to their human editor, not to an API refresh.
        league.clubs.filter(
            provider=league.provider, is_manual=False
        ).exclude(pk__in=seen).update(is_active=False)
        League.objects.filter(pk=league.pk).update(last_synced_at=now)
    return True
