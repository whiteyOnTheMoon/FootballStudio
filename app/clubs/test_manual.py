"""No-network tests for authenticated manual club creation (FS-011b/#25)."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .catalog import season_label, season_start
from .models import Club, Country, League


class ManualClubTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="manual@example.com", password="Strong-sample-password-2026!"
        )
        self.client.force_login(self.user)
        self.country = Country.objects.create(code="GB", name="England (UK)")
        self.league = League.objects.create(
            country=self.country, name="Premier League", tier=1,
            provider="openfootball", provider_id="en.1",
            catalog_season=season_label(season_start()),
        )
        self.second = League.objects.create(
            country=self.country, name="Championship", tier=2,
            provider="openfootball", provider_id="en.2",
            catalog_season=season_label(season_start()),
        )
        self.other_country = Country.objects.create(code="DE", name="Deutschland")
        self.german = League.objects.create(
            country=self.other_country, name="Bundesliga", tier=1,
            provider="openligadb", provider_id="bl1",
            catalog_season=season_label(season_start()),
        )
        self.url = reverse("clubs:manual")

    def payload(self, name="Added Town FC", league=None, country="GB"):
        return {
            "name": name,
            "league": league.pk if league else self.league.pk,
            "country": country,
        }

    def test_create_manual_club_and_select_it_immediately(self):
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 201)
        record = response.json()["club"]
        self.assertTrue(record["manual"])
        self.assertEqual(record["name"], "Added Town FC")
        club = Club.objects.get(pk=record["id"])
        self.assertTrue(club.is_manual)
        self.assertTrue(club.is_active)
        self.assertEqual(club.provider, "manual")
        self.assertEqual(club.league, self.league)
        selection = self.client.get(reverse("clubs:selection"), {
            "country": "GB", "league": self.league.pk, "club": club.pk,
        })
        self.assertEqual(selection.status_code, 200)
        self.assertEqual(selection.json()["selection"]["club_id"], club.pk)

    def test_duplicate_name_case_and_whitespace_rejected(self):
        first = self.client.post(self.url, self.payload(name="My   Club FC"))
        self.assertEqual(first.status_code, 201)
        second = self.client.post(self.url, self.payload(name="  MY CLUB FC  "))
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Club.objects.count(), 1)

    def test_existing_provider_club_must_not_be_overwritten(self):
        existing = Club.objects.create(
            league=self.league, name="Already Imported FC",
            provider="openfootball", provider_id="1234", is_manual=False,
        )
        result = self.client.post(self.url, self.payload(name="ALREADY IMPORTED FC"))
        self.assertEqual(result.status_code, 409)
        existing.refresh_from_db()
        self.assertFalse(existing.is_manual)
        self.assertEqual(existing.provider_id, "1234")

    def test_same_club_name_can_be_entered_in_another_league(self):
        first = self.client.post(self.url, self.payload())
        second = self.client.post(self.url, self.payload(league=self.second))
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.json()["club"]["id"], second.json()["club"]["id"])

    def test_country_and_league_mismatch_is_rejected(self):
        for content in (
            self.payload(league=self.german, country="GB"),
            self.payload(league=self.league, country="DE"),
        ):
            with self.subTest(data=content):
                self.assertEqual(self.client.post(self.url, content).status_code, 404)
        self.assertEqual(Club.objects.count(), 0)

    def test_blank_invalid_and_oversize_names_rejected(self):
        for name in ("", " ", "A", "X" * 161):
            with self.subTest(name=name[:12]):
                response = self.client.post(self.url, self.payload(name=name))
                self.assertEqual(response.status_code, 400)
        self.assertEqual(Club.objects.count(), 0)

    def test_missing_or_invalid_league_rejected(self):
        payload = self.payload()
        del payload["league"]
        self.assertEqual(self.client.post(self.url, payload).status_code, 400)
        self.assertEqual(
            self.client.post(self.url, self.payload(league=self.german, country="invalid")).status_code,
            400,
        )

    def test_login_required_and_only_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.logout()
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)
        self.assertEqual(Club.objects.count(), 0)

    def test_csrf_token_is_required(self):
        strict_client = Client(enforce_csrf_checks=True)
        strict_client.force_login(self.user)
        self.assertEqual(
            strict_client.post(self.url, self.payload()).status_code, 403
        )
        self.assertEqual(Club.objects.count(), 0)

    def test_no_external_api_or_fixed_club_is_needed(self):
        from unittest.mock import patch
        with patch("urllib.request.urlopen") as remote:
            response = self.client.post(self.url, self.payload(name="Hometown 2026"))
            self.assertEqual(response.status_code, 201)
            remote.assert_not_called()
