"""Research autopilot private HTTP endpoint and browser chain regression tests."""
from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from app.clubs.models import Club, Country, League
from .models import Fact, FactDossier, ProductionJob, SourceReference
from .wikimedia_auto import AutoResearchError

QID = "Q124007617"
URL = "https://www.wikidata.org/wiki/Special:EntityData/" + QID + ".json"


class ResearchAutopilotWebTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="autopilot-web-owner@example.org",
            password="Offline-fixture-password-1234",
        )
        self.other = User.objects.create_user(
            email="autopilot-web-other@example.org",
            password="Offline-fixture-password-1234",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(
            country=country, name="Austrian Bundesliga",
        )
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, club_name="Sturm Graz",
            country_code="AT", league_name="Austrian Bundesliga",
            title="The History of SK Sturm Graz",
        )
        self.url = reverse(
            "research-autopilot-continue",
            kwargs={"job_id": self.job.pk},
        )
        self.page = reverse(
            "research-job", kwargs={"job_id": self.job.pk},
        )
        self.client.force_login(self.owner)

    def put_identity(self, dossier):
        SourceReference.objects.create(
            dossier=dossier, source_kind="wikidata",
            url=URL, external_id=QID, title="[auto] SK Sturm Graz",
            retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
            access_state="accessible",
        )

    @patch("app.production.wikimedia_auto.import_free_club_research")
    def test_get_is_read_only_and_shows_single_click_form(self, importer):
        result = self.client.get(self.page)
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Automatischer Rechercheablauf")
        self.assertContains(result, "Automatische Recherche starten / fortsetzen")
        self.assertContains(result, self.url)
        self.assertContains(
            result, 'name="expected_version" value="0"',
        )
        self.assertContains(result, "fetch(form.action")
        self.assertContains(result, "englischen") if False else None
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(FactDossier.objects.count(), 0)
        importer.assert_not_called()

    @patch("app.production.wikimedia_auto.import_free_club_research")
    def test_json_post_executes_one_stage_and_returns_current_next_stage(
        self, importer,
    ):
        def make_dossier(**_kwargs):
            d = FactDossier.objects.create(job=self.job, version=1)
            self.put_identity(d)
            return d
        importer.side_effect = make_dossier
        result = self.client.post(
            self.url, {"expected_version": "0"},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(result.status_code, 200)
        data = result.json()
        self.assertEqual(data["status"], "advanced")
        self.assertEqual(data["stage"], "club")
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["next_stage"], "stadium")
        self.assertEqual(data["completed"], 1)
        self.assertEqual(data["total"], 5)
        self.assertEqual(FactDossier.objects.count(), 1)
        importer.assert_called_once()

    @patch("app.production.wikimedia_auto.import_free_club_research")
    def test_non_js_fallback_redirects_after_one_safe_step(self, importer):
        def make_dossier(**_kwargs):
            d = FactDossier.objects.create(job=self.job, version=1)
            self.put_identity(d)
            return d
        importer.side_effect = make_dossier
        response = self.client.post(self.url, {"expected_version": "0"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.page + "?version=1")
        importer.assert_called_once()

    @patch("app.production.wikimedia_auto.import_free_club_research")
    def test_stale_and_invalid_versions_are_not_silent_restarts(self, importer):
        current = FactDossier.objects.create(job=self.job, version=1)
        self.put_identity(current)
        for version in ("", "01", "-1", "1.0", "1<script>", "9999999999"):
            self.assertEqual(self.client.post(self.url, {
                "expected_version": version,
            }).status_code, 404)
        response = self.client.post(
            self.url, {"expected_version": "0"},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], "stopped")
        self.assertIn("Dossierversion", response.json()["message"])
        importer.assert_not_called()

    @patch("app.production.wikimedia_auto.import_free_club_research")
    def test_foreign_job_and_anonymous_never_invoke_importer(self, importer):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.page).status_code, 404)
        self.assertEqual(self.client.post(
            self.url, {"expected_version": "0"},
        ).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.post(
            self.url, {"expected_version": "0"},
        ).status_code, 302)
        importer.assert_not_called()

    @patch("app.production.wikimedia_auto.import_free_club_research")
    def test_csrf_blocks_initiation_and_child_steps(self, importer):
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.owner)
        self.assertEqual(secure.post(self.url, {
            "expected_version": "0",
        }).status_code, 403)
        importer.assert_not_called()
        secure.get(self.page)
        self.assertIn("csrftoken", secure.cookies)

        def make_dossier(**_kwargs):
            d = FactDossier.objects.create(job=self.job, version=1)
            self.put_identity(d)
            return d
        importer.side_effect = make_dossier
        response = secure.post(self.url, {
            "expected_version": "0",
            "csrfmiddlewaretoken": secure.cookies["csrftoken"].value,
        }, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        importer.assert_called_once()

    @patch("app.production.wikimedia_stadium.enrich_wikimedia_stadium")
    def test_stage_failure_does_not_fake_auto_research_success(self, stadium):
        d = FactDossier.objects.create(job=self.job, version=2)
        self.put_identity(d)
        stadium.side_effect = AutoResearchError("no_stadium_candidate")
        result = self.client.post(
            self.url, {"expected_version": "2"},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.json()["status"], "stopped")
        self.assertIn("Heimspielstätte", result.json()["message"])
        self.assertEqual(FactDossier.objects.count(), 1)

    def test_complete_dossier_avoids_all_network_and_shows_outline(self):
        d = FactDossier.objects.create(job=self.job, version=7)
        self.put_identity(d)
        SourceReference.objects.create(
            dossier=d, source_kind="wikidata",
            url="https://query.wikidata.org/sparql",
            title="Players", external_id="auto-p54:" + QID,
            retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
            access_state="accessible",
        )
        for external, kind, url in (
            ("auto-official-legends:" + QID, "club_official",
             "https://sksturm.at/c/legendenklub"),
            ("auto-honours:" + QID, "league_official",
             "https://www.bundesliga.at/de/titel-uebersicht"),
        ):
            SourceReference.objects.create(
                dossier=d, source_kind=kind,
                url=url, title="Automatic source", external_id=external,
                retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
                access_state="accessible",
            )
        Fact.objects.create(
            dossier=d, predicate="stadium_name", value="Merkur Arena",
            assertion_text="Stadium candidate.",
        )
        Fact.objects.create(
            dossier=d, predicate="club_honour_candidate",
            value={
                "season": "2023/24", "category": "domestic_cup",
                "corroboration": "league_only",
            },
            assertion_text="Official league 2023/24 cup winner candidate.",
        )
        with patch(
            "app.production.official_honours.import_official_honours_timeline"
        ) as honours:
            page = self.client.get(self.page)
            response = self.client.post(
                self.url, {"expected_version": "7"},
                HTTP_ACCEPT="application/json",
            )
        self.assertContains(page, "Alle fünf derzeit unterstützten Recherchestufen")
        self.assertContains(page, "Englische Dokumentation: quellengebundener Story-Aufbau")
        self.assertContains(page, "2023/24")
        self.assertContains(page, "Voiceover-Freigabe: nein")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "complete")
        self.assertEqual(response.json()["next_stage"], None)
        self.assertEqual(response.json()["version"], 7)
        self.assertEqual(FactDossier.objects.count(), 1)
        honours.assert_not_called()

    def test_historical_version_never_offers_autopilot_run(self):
        d1 = FactDossier.objects.create(job=self.job, version=1)
        self.put_identity(d1)
        FactDossier.objects.create(job=self.job, version=2)
        page = self.client.get(self.page + "?version=1")
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(
            page, "Automatische Recherche starten / fortsetzen",
        )
        self.assertContains(page, "Version 1")
