"""Private player-candidate search button: no manual names, safe CSRF POST."""
from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from app.clubs.models import Club, Country, League
from .models import Fact, FactDossier, ProductionJob, SourceReference
from .test_wikimedia_players import CLUB_QID, CLUB_URL, sample_people
from .wikimedia_auto import AutoResearchError


class PlayerCandidatesWebTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="people-ui-owner@example.org",
            password="Test-only-password-2026",
        )
        self.other = User.objects.create_user(
            email="people-ui-other@example.org",
            password="Test-only-password-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club,
            country_code="AT", league_name="Bundesliga",
            club_name="Sturm Graz", title="A Sourced Club History",
        )
        self.dossier = FactDossier.objects.create(
            job=self.job, version=4,
        )
        SourceReference.objects.create(
            dossier=self.dossier, source_kind="wikidata",
            url=CLUB_URL, title="[auto] SK Sturm Graz",
            external_id=CLUB_QID,
            retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
            access_state="accessible",
        )
        Fact.objects.create(
            dossier=self.dossier, predicate="founded_year",
            value=1909, assertion_text="The club was founded in 1909.",
        )
        self.research = reverse(
            "research-job", kwargs={"job_id": self.job.pk},
        )
        self.endpoint = reverse(
            "research-auto-wikimedia-players",
            kwargs={"job_id": self.job.pk},
        )
        self.client.force_login(self.owner)

    def test_preview_only_exposes_button_if_club_identified(self):
        page = self.client.get(self.research + "?version=4")
        self.assertContains(page, self.endpoint)
        self.assertContains(page, "Spieler und mögliche Vereinslegenden automatisch suchen")
        self.assertContains(page, 'name="expected_version" value="4"')
        self.assertNotContains(page, 'name="person_qid"')
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.wikimedia_players.discover_wikidata_players")
    def test_one_click_fetches_and_displays_unverified_names(self, search):
        search.return_value = sample_people()
        out = self.client.post(self.endpoint, {
            "expected_version": "4",
        })
        self.assertEqual(out.status_code, 302)
        self.assertEqual(out["Location"], self.research + "?version=5")
        page = self.client.get(out["Location"])
        self.assertContains(page, "Mario Haas")
        self.assertContains(page, "Ivica Vastić")
        self.assertContains(page, "Keiner der Namen")
        self.assertContains(page, "Wikidata-Bezug prüfen")
        self.assertNotContains(
            page, "Spieler und mögliche Vereinslegenden automatisch suchen",
        )
        self.assertEqual(FactDossier.objects.count(), 2)
        self.assertEqual(
            Fact.objects.filter(
                predicate="club_player_candidate",
                verification_state="verified",
            ).count(), 0,
        )
        search.assert_called_once_with(club_qid=CLUB_QID)

    @patch("app.production.wikimedia_players.discover_wikidata_players")
    def test_get_never_triggers_external_search(self, search):
        self.assertEqual(self.client.get(self.endpoint).status_code, 405)
        search.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.wikimedia_players.discover_wikidata_players")
    def test_foreign_owner_denied_before_external_query(self, search):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.research).status_code, 404)
        self.assertEqual(self.client.post(self.endpoint, {
            "expected_version": "4",
        }).status_code, 404)
        search.assert_not_called()

    def test_anonymous_redirected(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.endpoint, {
            "expected_version": "4",
        }).status_code, 302)

    @patch("app.production.wikimedia_players.discover_wikidata_players")
    def test_invalid_and_stale_versions_never_call_network(self, search):
        for value in ("", "04", "-1", "0", "abc", "4<script>", "9999999999"):
            with self.subTest(value=value):
                self.assertEqual(self.client.post(self.endpoint, {
                    "expected_version": value,
                }).status_code, 404)
        self.assertEqual(self.client.post(self.endpoint, {
            "expected_version": "3",
        }).status_code, 409)
        search.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.wikimedia_players.discover_wikidata_players")
    def test_network_failure_does_not_create_research_version(self, search):
        search.side_effect = AutoResearchError("network_error")
        result = self.client.post(self.endpoint, {
            "expected_version": "4",
        })
        self.assertEqual(result.status_code, 503)
        self.assertNotIn(b"Traceback", result.content)
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.wikimedia_players.discover_wikidata_players")
    def test_retry_is_idempotent_and_does_not_refetch(self, search):
        search.return_value = sample_people()
        first = self.client.post(self.endpoint, {
            "expected_version": "4",
        })
        second = self.client.post(self.endpoint, {
            "expected_version": "4",
        })
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(FactDossier.objects.count(), 2)
        search.assert_called_once()

    @patch("app.production.wikimedia_players.discover_wikidata_players")
    def test_csrf_protects_one_outbound_query(self, search):
        search.return_value = sample_people()
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.owner)
        self.assertEqual(secure.post(self.endpoint, {
            "expected_version": "4",
        }).status_code, 403)
        search.assert_not_called()
        secure.get(self.research)
        self.assertIn("csrftoken", secure.cookies)
        ok = secure.post(self.endpoint, {
            "expected_version": "4",
            "csrfmiddlewaretoken": secure.cookies["csrftoken"].value,
        })
        self.assertEqual(ok.status_code, 302)
        search.assert_called_once()
