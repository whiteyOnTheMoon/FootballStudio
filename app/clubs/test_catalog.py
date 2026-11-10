"""Offline federation-picker tests. Deliberately no requests to external services."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Club, Confederation, Country, League


class GlobalOfflineCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_world_catalog", verbosity=0)
        cls.user = get_user_model().objects.create_user(
            email="world-picker@example.com", password="Test-strong-passphrase-2026!"
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_all_uefa_55_and_six_confederations_are_seeded(self):
        self.assertEqual(Confederation.objects.count(), 6)
        self.assertEqual(Country.objects.filter(confederation__code="UEFA").count(), 55)
        self.assertEqual(
            set(Confederation.objects.values_list("code", flat=True)),
            {"UEFA", "CAF", "AFC", "OFC", "CONCACAF", "CONMEBOL"},
        )
        self.assertTrue(Country.objects.filter(code="SCO").exists())
        self.assertTrue(Country.objects.filter(code="WAL").exists())
        self.assertTrue(Country.objects.filter(code="NIR").exists())
        self.assertTrue(Country.objects.filter(code="GB", name="England").exists())
        self.assertGreater(Country.objects.count(), 100)

    def test_uefa_two_league_references_except_actual_single_tier_exceptions(self):
        for association in Country.objects.filter(confederation__code="UEFA"):
            tiers = set(association.leagues.values_list("tier", flat=True))
            if association.code == "LI":
                self.assertFalse(tiers)
            elif association.code in {"GI", "SM"}:
                self.assertEqual(tiers, {1})
            else:
                self.assertTrue(
                    {1, 2}.issubset(tiers), f"{association.name} missing tier 1/2"
                )

    def test_snapshot_contains_real_clubs_only_for_sourced_leagues(self):
        self.assertEqual(
            League.objects.filter(coverage_status="snapshot").count(), 16
        )
        rows = [
            ("GB", 1, 20), ("GB", 2, 24), ("DE", 1, 18),
            ("ES", 1, 20), ("FR", 1, 18), ("IT", 1, 20),
            ("NL", 1, 18), ("PT", 1, 18),
            ("DE", 2, 18), ("DE", 3, 20), ("AT", 1, 12),
            ("SCO", 1, 12), ("CH", 1, 12), ("CZ", 1, 16),
            ("GR", 1, 14), ("TR", 1, 18),
        ]
        for code, tier, count in rows:
            with self.subTest(code=code, tier=tier):
                league = League.objects.get(country__code=code, tier=tier)
                self.assertEqual(league.clubs.count(), count)
                self.assertEqual(league.catalog_season, "2026-27")
                self.assertIn("openfootball", league.source_url)
        self.assertEqual(
            League.objects.get(country__code="WAL", tier=1).clubs.count(), 0
        )

    def test_no_network_even_when_switching_region_and_fetching_clubs(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            confeds = self.client.get(reverse("clubs:confederations"))
            self.assertEqual(confeds.status_code, 200)
            self.assertEqual(len(confeds.json()["confederations"]), 6)
            countries = self.client.get(
                reverse("clubs:countries"), {"confederation": "UEFA"}
            )
            self.assertEqual(countries.status_code, 200)
            self.assertEqual(len(countries.json()["countries"]), 55)
            leagues = self.client.get(reverse("clubs:leagues"), {"country": "GB"})
            self.assertEqual(leagues.status_code, 200)
            league_id = leagues.json()["leagues"][0]["id"]
            response = self.client.get(reverse("clubs:clubs"), {
                "country": "GB", "league": league_id,
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["clubs"]), 20)

    def test_confederation_filters_are_correct(self):
        for confed in Confederation.objects.values_list("code", flat=True):
            response = self.client.get(
                reverse("clubs:countries"), {"confederation": confed}
            )
            self.assertEqual(response.status_code, 200)
            for row in response.json()["countries"]:
                self.assertEqual(
                    Country.objects.get(code=row["code"]).confederation.code,
                    confed,
                )
        self.assertEqual(
            self.client.get(reverse("clubs:countries"), {"confederation": "NOPE"}).status_code,
            404,
        )

    def test_empty_league_is_visible_but_never_populated_with_fake_clubs(self):
        league = League.objects.get(country__code="WAL", tier=1)
        self.assertEqual(league.coverage_status, "reference")
        response = self.client.get(reverse("clubs:clubs"), {
            "country": "WAL", "league": league.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["clubs"], [])
        self.assertIn("not yet been imported", response.json()["warning"])

    def test_liechtenstein_is_not_given_a_fictitious_league(self):
        response = self.client.get(reverse("clubs:leagues"), {"country": "LI"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["leagues"], [])
        self.assertIn("no domestic league", response.json()["notice"])

    def test_api_rejects_forged_parent_league_and_club(self):
        english = League.objects.get(country__code="GB", tier=1)
        club = english.clubs.first()
        self.assertIsNotNone(club)
        valid = self.client.get(reverse("clubs:selection"), {
            "country": "GB", "league": english.pk, "club": club.pk,
        })
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()["selection"]["confederation"], "UEFA")
        invalid = self.client.get(reverse("clubs:selection"), {
            "country": "DE", "league": english.pk, "club": club.pk,
        })
        self.assertEqual(invalid.status_code, 404)

    def test_own_club_can_be_selected_in_a_home_nation(self):
        scotland = League.objects.get(country__code="SCO", tier=1)
        manual = Club.objects.create(league=scotland, name="Example Scottish FC")
        response = self.client.get(reverse("clubs:selection"), {
            "country": "SCO", "league": scotland.pk, "club": manual.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selection"]["country_code"], "SCO")

    def test_seed_is_idempotent_and_preserves_human_created_clubs(self):
        league = League.objects.get(country__code="GB", tier=1)
        club = Club.objects.create(league=league, name="Preserved Local FC")
        before = (Country.objects.count(), League.objects.count(), Club.objects.count())
        call_command("seed_world_catalog", verbosity=0)
        after = (Country.objects.count(), League.objects.count(), Club.objects.count())
        self.assertEqual(before, after)
        club.refresh_from_db()
        self.assertTrue(club.is_manual)
        self.assertTrue(club.is_active)

    def test_anonymous_users_cannot_browse_the_catalog(self):
        self.client.logout()
        for name in (
            "clubs:confederations", "clubs:countries", "clubs:leagues",
            "clubs:clubs", "clubs:selection"
        ):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 302)
