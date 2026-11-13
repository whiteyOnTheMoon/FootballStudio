"""Owner-only free Wikimedia research button and CSRF checks."""
from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from app.clubs.models import Club, Country, League
from .models import FactDossier, ProductionJob, SourceReference, Fact
from .wikimedia_auto import AutoResearchError


class FreeResearchWebTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="free-research-owner@example.org",
            password="Test-only-passphrase-2026",
        )
        self.other = User.objects.create_user(
            email="free-research-other@example.org",
            password="Test-only-passphrase-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, country_code="AT",
            league_name="Austrian Bundesliga", club_name="Sturm Graz",
            title="An English Documentary",
        )
        FactDossier.objects.create(job=self.job, version=2)
        self.url = reverse(
            "research-auto-wikimedia", kwargs={"job_id": self.job.pk},
        )
        self.research = reverse("research-job", kwargs={"job_id": self.job.pk})
        self.client.force_login(self.owner)

    def data(self):
        return {
            "qid": "Q124007617", "label": "SK Sturm Graz",
            "wikidata_url":
                "https://www.wikidata.org/wiki/Special:EntityData/Q124007617.json",
            "founded_year_candidate": 1909,
            "wikipedia_url": "https://en.wikipedia.org/wiki/SK_Sturm_Graz",
            "wikipedia_intro_mentions_year": True,
            "retrieved_at": datetime(2026, 11, 13, tzinfo=timezone.utc),
        }

    def test_dossier_offers_auto_research_button_without_manual_qid(self):
        response = self.client.get(self.research)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vereinsdaten automatisch recherchieren")
        self.assertContains(response, self.url)
        self.assertContains(response, 'name="expected_version" value="2"')
        self.assertNotContains(response, 'name="qid"')
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_actual_post_imports_new_version_and_shows_fact_as_unverified(self, discover):
        discover.return_value = self.data()
        response = self.client.post(self.url, {"expected_version": "2"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.research + "?version=3")
        overview = self.client.get(response["Location"])
        self.assertContains(overview, "Fakt")
        self.assertContains(overview, "1909")
        self.assertContains(overview, "Ungeprüft")
        self.assertEqual(FactDossier.objects.count(), 2)
        self.assertEqual(Fact.objects.get().verification_state, "unverified")
        self.assertEqual(SourceReference.objects.count(), 2)

    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_get_is_read_only_method_not_allowed(self, discover):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(FactDossier.objects.count(), 1)
        discover.assert_not_called()

    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_foreign_owner_denied_before_network(self, discover):
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.url, {
            "expected_version": "2",
        }).status_code, 404)
        discover.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    def test_anonymous_login_redirect(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {
            "expected_version": "2",
        }).status_code, 302)

    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_bad_versions_rejected_without_network_or_writes(self, discover):
        for value in ("", "-1", "02", "abc", "1.1", "99999999999", "2<script>"):
            with self.subTest(value=value):
                self.assertEqual(self.client.post(self.url, {
                    "expected_version": value,
                }).status_code, 404)
        self.assertEqual(FactDossier.objects.count(), 1)
        discover.assert_not_called()

    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_stale_version_and_ambiguous_entity_not_written(self, discover):
        self.assertEqual(self.client.post(self.url, {
            "expected_version": "1",
        }).status_code, 409)
        discover.assert_not_called()
        discover.side_effect = AutoResearchError("ambiguous_entity")
        response = self.client.post(self.url, {
            "expected_version": "2",
        })
        self.assertEqual(response.status_code, 409)
        self.assertContains(
            response, "Mehrere passende Vereine gefunden", status_code=409,
        )
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_network_error_returns_safe_message_with_no_api_text(self, discover):
        discover.side_effect = AutoResearchError("network_error")
        response = self.client.post(self.url, {
            "expected_version": "2",
        })
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"Traceback", response.content)
        self.assertIn("Wikimedia".encode(), response.content)
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.wikimedia_auto.discover_free_club_research")
    def test_csrf_required_for_actual_network_trigger(self, discover):
        discover.return_value = self.data()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        self.assertEqual(csrf_client.post(self.url, {
            "expected_version": "2",
        }).status_code, 403)
        discover.assert_not_called()
        csrf_client.get(self.research)
        self.assertIn("csrftoken", csrf_client.cookies)
        response = csrf_client.post(self.url, {
            "expected_version": "2",
            "csrfmiddlewaretoken": csrf_client.cookies["csrftoken"].value,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FactDossier.objects.count(), 2)
        discover.assert_called_once()
