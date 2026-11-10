"""No-network tests for M1 country → league → club API and source adapters."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .catalog import (
    CatalogUnavailable, discover_countries, season_label, season_start,
    sync_league_teams, teams_for_league,
)
from .models import Club, Country, League


def mock_public_api(url):
    """Season-aware fake API responses; NEVER hardcode these team names in app code."""
    year = season_start()
    season = season_label(year)
    if f"contents/{season}" in url:
        # Third English division is deliberately absent for this season.
        return [
            {"name": "en.1.json", "size": 1000},
            {"name": "en.2.json", "size": 1000},
            {"name": "de.1.json", "size": 1000},
        ]
    if f"getavailableleagues/{year}" in url:
        return [
            {"leagueShortcut": "bl1"},
            {"leagueShortcut": "bl2"},
            {"leagueShortcut": "bl3"},
        ]
    if f"{season}/en.1.json" in url:
        return {
            "name": "Premier League fixture data",
            "matches": [
                {"team1": f"Premier FC {i:02d}", "team2": f"Premier FC {(i + 1) % 20:02d}"}
                for i in range(20)
            ],
        }
    if f"{season}/en.2.json" in url:
        return {
            "name": "Championship fixture data",
            "matches": [
                {"team1": f"Championship FC {i:02d}",
                 "team2": f"Championship FC {(i + 1) % 24:02d}"}
                for i in range(24)
            ],
        }
    if f"getavailableteams/bl1/{year}" in url:
        return [{"teamId": i + 1000, "teamName": f"Bundesliga FC {i:02d}"} for i in range(18)]
    if f"getavailableteams/bl2/{year}" in url:
        return [{"teamId": i + 2000, "teamName": f"2 Bundesliga FC {i:02d}"} for i in range(18)]
    if f"getavailableteams/bl3/{year}" in url:
        return [{"teamId": i + 3000, "teamName": f"3 Liga FC {i:02d}"} for i in range(20)]
    raise AssertionError(f"Unexpected catalog request: {url}")


class CatalogPickerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            email="picker@example.com", password="Test-strong-password-2026!"
        )
        self.client.force_login(self.user)

    @patch("app.clubs.catalog.fetch_json", side_effect=mock_public_api)
    def test_two_real_source_backed_tiers_per_supported_country(self, fetch):
        response = self.client.get(reverse("clubs:countries"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["season"], season_label(season_start()))
        self.assertEqual({x["code"] for x in data["countries"]}, {"GB", "DE"})
        self.assertEqual(Club.objects.count(), 0)  # No preset pilot clubs.
        england = Country.objects.get(code="GB")
        germany = Country.objects.get(code="DE")
        self.assertEqual(list(england.leagues.values_list("tier", flat=True)), [1, 2])
        self.assertEqual(list(germany.leagues.values_list("tier", flat=True)), [1, 2, 3])
        self.assertEqual(fetch.call_count, 2)
        self.client.get(reverse("clubs:countries"))
        self.assertEqual(fetch.call_count, 2)  # No redundant live calls on cache hit.

    @patch("app.clubs.catalog.fetch_json", side_effect=mock_public_api)
    def test_filtered_leagues_and_multiple_clubs_per_league(self, fetch):
        self.client.get(reverse("clubs:countries"))
        gb_leagues = self.client.get(
            reverse("clubs:leagues"), {"country": "GB"}
        ).json()["leagues"]
        de_leagues = self.client.get(
            reverse("clubs:leagues"), {"country": "DE"}
        ).json()["leagues"]
        self.assertEqual([x["name"] for x in gb_leagues], ["Premier League", "Championship"])
        self.assertEqual([x["tier"] for x in de_leagues], [1, 2, 3])
        self.assertTrue({x["id"] for x in gb_leagues}.isdisjoint(
            {x["id"] for x in de_leagues}
        ))
        premier = self.client.get(
            reverse("clubs:clubs"),
            {"country": "GB", "league": gb_leagues[0]["id"]},
        )
        self.assertEqual(premier.status_code, 200)
        self.assertEqual(len(premier.json()["clubs"]), 20)
        self.assertTrue(all(not x["manual"] for x in premier.json()["clubs"]))
        championship = self.client.get(
            reverse("clubs:clubs"),
            {"country": "GB", "league": gb_leagues[1]["id"]},
        )
        self.assertEqual(len(championship.json()["clubs"]), 24)
        german = self.client.get(
            reverse("clubs:clubs"),
            {"country": "DE", "league": de_leagues[0]["id"]},
        )
        self.assertEqual(len(german.json()["clubs"]), 18)
        # A German league ID cannot be loaded under an English country.
        mismatched = self.client.get(
            reverse("clubs:clubs"),
            {"country": "GB", "league": de_leagues[0]["id"]},
        )
        self.assertEqual(mismatched.status_code, 404)

    @patch("app.clubs.catalog.fetch_json", side_effect=mock_public_api)
    def test_server_validates_selected_club_parent_relationships(self, fetch):
        self.client.get(reverse("clubs:countries"))
        english = League.objects.get(country__code="GB", tier=1)
        second = League.objects.get(country__code="GB", tier=2)
        self.client.get(reverse("clubs:clubs"), {"country": "GB", "league": english.pk})
        team = english.clubs.first()
        self.assertIsNotNone(team)
        selected = self.client.get(reverse("clubs:selection"), {
            "country": "GB", "league": english.pk, "club": team.pk,
        })
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.json()["selection"]["club_id"], team.pk)
        self.assertFalse(selected.json()["job_enabled"])
        for context in (
            {"country": "DE", "league": english.pk, "club": team.pk},
            {"country": "GB", "league": second.pk, "club": team.pk},
            {"country": "GB", "league": english.pk, "club": 999999},
        ):
            with self.subTest(context=context):
                self.assertEqual(
                    self.client.get(reverse("clubs:selection"), context).status_code,
                    404,
                )

    def test_invalid_params_do_not_trigger_external_requests(self):
        with patch("app.clubs.catalog.fetch_json") as remote:
            self.assertEqual(
                self.client.get(reverse("clubs:leagues"), {"country": "FR"}).status_code,
                400,
            )
            self.assertEqual(
                self.client.get(reverse("clubs:clubs"), {
                    "country": "GB", "league": "../etc/passwd",
                }).status_code,
                400,
            )
            self.assertEqual(
                self.client.get(reverse("clubs:selection"), {
                    "country": "GB", "league": "a", "club": "1",
                }).status_code,
                400,
            )
            remote.assert_not_called()

    @patch("app.clubs.catalog.fetch_json", side_effect=mock_public_api)
    def test_manual_club_is_never_overwritten_by_api_import(self, fetch):
        self.client.get(reverse("clubs:countries"))
        league = League.objects.get(country__code="GB", tier=1)
        manual = Club.objects.create(league=league, name="Premier FC 00")
        self.assertTrue(manual.is_manual)
        sync_league_teams(league)
        manual.refresh_from_db()
        self.assertTrue(manual.is_manual)
        self.assertEqual(manual.provider, "manual")
        self.assertTrue(manual.is_active)
        self.assertEqual(league.clubs.filter(is_active=True).count(), 20)

    @patch("app.clubs.catalog.fetch_json", side_effect=mock_public_api)
    def test_provider_failure_shows_explicit_stale_warning(self, fetch):
        self.client.get(reverse("clubs:countries"))
        league = League.objects.get(country__code="GB", tier=1)
        sync_league_teams(league)
        League.objects.filter(pk=league.pk).update(last_synced_at=None)
        with patch(
            "app.clubs.catalog.fetch_json",
            side_effect=CatalogUnavailable("unavailable"),
        ):
            response = self.client.get(reverse("clubs:clubs"), {
                "country": "GB", "league": league.pk,
            })
        self.assertEqual(response.status_code, 200)
        self.assertIn("may be outdated", response.json()["warning"])
        self.assertEqual(len(response.json()["clubs"]), 20)

    @patch("app.clubs.catalog.fetch_json", side_effect=CatalogUnavailable("unavailable"))
    def test_no_catalog_is_unavailable_without_fabricating_data(self, fetch):
        response = self.client.get(reverse("clubs:countries"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Country.objects.count(), 0)
        self.assertEqual(Club.objects.count(), 0)

    def test_anonymous_cannot_read_any_catalog_endpoint(self):
        self.client.logout()
        for name in ("clubs:countries", "clubs:leagues", "clubs:clubs", "clubs:selection"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/", response.url)

    @patch("app.clubs.catalog.fetch_json")
    def test_partial_free_tier_result_cannot_pass_as_full_league(self, fetch):
        self.client.get(reverse("clubs:countries"))  # response itself may be empty.
        country = Country.objects.create(code="GB", name="England (UK)")
        league = League.objects.create(
            country=country, name="Premier League", tier=1,
            provider="openfootball", provider_id="en.1",
            catalog_season=season_label(season_start()),
        )
        fetch.return_value = {
            "matches": [
                {"team1": "One FC", "team2": "Two FC"},
                {"team1": "Three FC", "team2": "Four FC"},
            ]
        }
        with self.assertRaises(CatalogUnavailable):
            teams_for_league(league, season_start())
        self.assertEqual(Club.objects.count(), 0)

    @patch("app.clubs.catalog.fetch_json", side_effect=mock_public_api)
    def test_second_and_third_english_tiers_are_not_invented(self, fetch):
        countries, _ = discover_countries()
        england = next(x for x in countries if x.code == "GB")
        self.assertEqual(
            list(england.leagues.values_list("provider_id", flat=True)),
            ["en.1", "en.2"],
        )

    @patch("app.clubs.catalog.fetch_json")
    def test_no_country_with_just_one_available_tier_is_advertised(self, fetch):
        year = season_start()
        def only_top(url):
            if "contents/" in url:
                return [{"name": "en.1.json", "size": 42}]
            if "getavailableleagues" in url:
                return [{"leagueShortcut": "bl1"}]
            raise AssertionError(url)
        fetch.side_effect = only_top
        response = self.client.get(reverse("clubs:countries"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(League.objects.count(), 0)
