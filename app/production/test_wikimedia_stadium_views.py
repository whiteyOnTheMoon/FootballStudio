"""Owner-only free P115 stadium enrichment flow from a previously imported club."""
from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from app.clubs.models import Club, Country, League

from .models import Fact, FactDossier, ProductionJob, SourceReference
from .test_wikimedia_stadium import CLUB_QID, CLUB_URL, sample_venue
from .wikimedia_auto import AutoResearchError


class StadiumEnrichmentWebTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="stadium-web-owner@example.org",
            password="Test-only-password-2026",
        )
        self.other = User.objects.create_user(
            email="stadium-web-other@example.org",
            password="Test-only-password-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, country_code="AT",
            league_name="Austrian Bundesliga",
            club_name="Sturm Graz", title="A Sourced Story",
        )
        self.dossier = FactDossier.objects.create(job=self.job, version=3)
        SourceReference.objects.create(
            dossier=self.dossier, url=CLUB_URL,
            source_kind="wikidata", title="[auto] SK Sturm Graz",
            external_id=CLUB_QID,
            retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
            access_state="accessible",
        )
        Fact.objects.create(
            dossier=self.dossier, predicate="founded_year",
            value=1909, assertion_text="The club was founded in 1909.",
        )
        self.url = reverse(
            "research-auto-wikimedia-stadium",
            kwargs={"job_id": self.job.pk},
        )
        self.research_url = reverse(
            "research-job", kwargs={"job_id": self.job.pk},
        )
        self.client.force_login(self.owner)

    def test_research_page_offers_stadium_without_manual_ids(self):
        result = self.client.get(self.research_url + "?version=3")
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Weitere Fakten automatisch recherchieren: Stadion")
        self.assertContains(result, self.url)
        self.assertContains(
            result, 'name="expected_version" value="3"',
        )
        self.assertNotContains(result, 'name="venue_qid"')
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_post_adds_stadium_and_exposes_unverified_fact(self, discover):
        discover.return_value = sample_venue()
        result = self.client.post(self.url, {"expected_version": "3"})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(
            result["Location"], self.research_url + "?version=4",
        )
        rendered = self.client.get(result["Location"])
        self.assertContains(rendered, "Merkur Arena")
        self.assertContains(rendered, "1909")
        self.assertContains(rendered, "Ungeprüft")
        self.assertNotContains(
            rendered, "Weitere Fakten automatisch recherchieren: Stadion",
        )
        self.assertEqual(FactDossier.objects.count(), 2)
        self.assertEqual(
            Fact.objects.filter(predicate="stadium_name").count(), 1,
        )

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_get_does_not_trigger_lookup_or_db_write(self, discover):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(FactDossier.objects.count(), 1)
        discover.assert_not_called()

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_invalid_or_stale_post_does_not_dispatch_network(self, discover):
        for raw in ("", "-1", "03", "abc", "0", "3<script>", "9999999999"):
            with self.subTest(raw=raw):
                self.assertEqual(self.client.post(self.url, {
                    "expected_version": raw,
                }).status_code, 404)
        self.assertEqual(self.client.post(self.url, {
            "expected_version": "2",
        }).status_code, 409)
        discover.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_no_stadium_or_multiple_venues_are_not_invented(self, discover):
        for code in ("no_stadium_candidate", "ambiguous_stadium"):
            discover.side_effect = AutoResearchError(code)
            result = self.client.post(self.url, {"expected_version": "3"})
            self.assertEqual(result.status_code, 409)
            self.assertEqual(FactDossier.objects.count(), 1)
            self.assertEqual(
                Fact.objects.filter(predicate="stadium_name").count(), 0,
            )

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_foreign_user_denied_before_network(self, discover):
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(self.research_url).status_code, 404,
        )
        self.assertEqual(self.client.post(self.url, {
            "expected_version": "3",
        }).status_code, 404)
        discover.assert_not_called()

    def test_anonymous_user_must_log_in(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {
            "expected_version": "3",
        }).status_code, 302)

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_csrf_is_required_for_outbound_network_lookup(self, discover):
        discover.return_value = sample_venue()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.url, {
            "expected_version": "3",
        }).status_code, 403)
        discover.assert_not_called()
        client.get(self.research_url)
        self.assertIn("csrftoken", client.cookies)
        response = client.post(self.url, {
            "expected_version": "3",
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        })
        self.assertEqual(response.status_code, 302)
        discover.assert_called_once()

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_repeat_enrichment_uses_saved_data_without_network(self, discover):
        discover.return_value = sample_venue()
        first = self.client.post(self.url, {"expected_version": "3"})
        self.assertEqual(first.status_code, 302)
        second = self.client.post(self.url, {"expected_version": "3"})
        self.assertEqual(second.status_code, 302)
        self.assertEqual(discover.call_count, 1)
        self.assertEqual(FactDossier.objects.count(), 2)

    @patch("app.production.wikimedia_stadium.discover_wikidata_stadium")
    def test_wikidata_network_outage_is_graceful(self, discover):
        discover.side_effect = AutoResearchError("network_error")
        result = self.client.post(self.url, {"expected_version": "3"})
        self.assertEqual(result.status_code, 503)
        self.assertNotIn(b"Traceback", result.content)
        self.assertEqual(FactDossier.objects.count(), 1)
