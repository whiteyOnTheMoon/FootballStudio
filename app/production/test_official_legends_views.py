"""Official legend crosscheck web action: current dossier, CSRF, owner and UI."""
from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from app.clubs.models import Club, Country, League
from .models import (
    Fact, FactDossier, ProductionJob, SourceConfirmation, SourceReference,
)
from .official_legends import _clean_person
from .safe_official_fetch import WebsiteFetchError

HOME = "https://sksturm.at/"
CLUB_QID = "Q124007617"
LEGENDS = "https://sksturm.at/c/legendenklub"


class OfficialLegendsWebTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="legends-web-owner@example.org",
            password="Temporary-only-test-password-2026",
        )
        self.other = User.objects.create_user(
            email="legends-web-other@example.org",
            password="Temporary-only-test-password-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, country_code="AT",
            league_name="Austrian Bundesliga", club_name="Sturm Graz",
            title="A Documentary About Legends",
        )
        self.dossier = FactDossier.objects.create(job=self.job, version=5)
        SourceReference.objects.create(
            dossier=self.dossier, source_kind="wikidata",
            url=(
                "https://www.wikidata.org/wiki/Special:EntityData/"
                + CLUB_QID + ".json"
            ),
            title="[auto] SK Sturm Graz", external_id=CLUB_QID,
            retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
            access_state="accessible",
        )
        source = SourceReference.objects.create(
            dossier=self.dossier, source_kind="club_official",
            url=HOME, title="Official SK Sturm website",
            retrieved_at=datetime(2026, 11, 11, tzinfo=timezone.utc),
            access_state="accessible",
        )
        SourceConfirmation.objects.create(
            source=source, reviewer=self.owner,
            checked_at=datetime(2026, 11, 11, tzinfo=timezone.utc),
            confirmed_domain="sksturm.at", terms_confirmed=True,
            identity_confirmed=True, access_confirmed=True,
            basis="The official homepage of SK Sturm Graz, confirmed.",
        )
        for name, qid in (
            ("Mario Haas", "Q471837"),
            ("Ivica Vastić", "Q295065"),
        ):
            Fact.objects.create(
                dossier=self.dossier, predicate="club_player_candidate",
                value={"name": name, "person_qid": qid, "sitelinks": 30},
                assertion_text=f"Wikidata records a team association for {name}.",
            )
        self.url = reverse(
            "research-auto-official-legends", kwargs={"job_id": self.job.pk},
        )
        self.research = reverse(
            "research-job", kwargs={"job_id": self.job.pk},
        )
        self.client.force_login(self.owner)

    def fake_result(self):
        return LEGENDS, {
            "player": {
                "mario haas": "Mario Haas",
                "ivica vastić": "Ivica Vastić",
            },
            "trainer": {
                "ivica osim": "Ivica Osim",
                "franco foda": "Franco Foda",
            },
        }

    def test_button_visible_on_latest_auto_player_dossier(self):
        page = self.client.get(self.research)
        self.assertEqual(page.status_code, 200)
        # The P54 import marker is the prerequisite for offering the button.
        self.assertNotContains(page, "Offizielle Vereinslegenden automatisch abgleichen")
        SourceReference.objects.create(
            dossier=self.dossier, source_kind="wikidata",
            url="https://query.wikidata.org/sparql",
            title="Wikidata player candidate discovery",
            external_id="auto-p54:" + CLUB_QID,
            retrieved_at=datetime.now(timezone.utc),
            access_state="accessible",
        )
        page = self.client.get(self.research)
        self.assertContains(page, "Offizielle Vereinslegenden automatisch abgleichen")
        self.assertContains(page, self.url)
        self.assertContains(
            page, 'name="expected_version" value="5"',
        )
        self.assertNotContains(page, 'name="club_qid"')

    @patch("app.production.official_legends._read_official_legends")
    def test_browser_post_adds_version_with_official_player_and_coach_lists(
        self, reader,
    ):
        reader.return_value = self.fake_result()
        result = self.client.post(self.url, {"expected_version": "5"})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(result["Location"], self.research + "?version=6")
        page = self.client.get(result["Location"])
        self.assertContains(page, "Abgleich mit dem offiziellen Vereins-Legendenklub")
        self.assertContains(page, "Mario Haas")
        self.assertContains(page, "Ivica Osim")
        self.assertContains(page, "Franco Foda")
        self.assertContains(page, "Originale Vereinsliste")
        self.assertNotContains(page, "Offizielle Vereinslegenden automatisch abgleichen")
        self.assertEqual(FactDossier.objects.count(), 2)
        self.assertEqual(
            Fact.objects.filter(verification_state="verified").count(), 0,
        )

    @patch("app.production.official_legends._read_official_legends")
    def test_get_read_only_and_user_isolated(self, reader):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.research).status_code, 404)
        self.assertEqual(self.client.post(self.url, {
            "expected_version": "5",
        }).status_code, 404)
        reader.assert_not_called()

    def test_anonymous_redirect(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {
            "expected_version": "5",
        }).status_code, 302)

    @patch("app.production.official_legends._read_official_legends")
    def test_invalid_stale_versions_reject_before_network(self, reader):
        for raw in ("", "05", "-1", "a", "9999999999", "5<script>"):
            with self.subTest(raw=raw):
                self.assertEqual(self.client.post(self.url, {
                    "expected_version": raw,
                }).status_code, 404)
        self.assertEqual(self.client.post(self.url, {
            "expected_version": "4",
        }).status_code, 409)
        reader.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.official_legends._read_official_legends")
    def test_robots_block_is_safely_shown_without_partial_data(self, reader):
        reader.side_effect = WebsiteFetchError("robots_disallowed")
        result = self.client.post(self.url, {"expected_version": "5"})
        self.assertEqual(result.status_code, 503)
        self.assertContains(
            result, "untersagt den automatischen Abruf", status_code=503,
        )
        self.assertNotIn(b"Traceback", result.content)
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.official_legends._read_official_legends")
    def test_retry_is_idempotent_without_fetch(self, reader):
        reader.return_value = self.fake_result()
        first = self.client.post(self.url, {"expected_version": "5"})
        second = self.client.post(self.url, {"expected_version": "5"})
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(FactDossier.objects.count(), 2)
        reader.assert_called_once()

    @patch("app.production.official_legends._read_official_legends")
    def test_csrf_must_pass_before_network(self, reader):
        reader.return_value = self.fake_result()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.url, {
            "expected_version": "5",
        }).status_code, 403)
        reader.assert_not_called()
        client.get(self.research)
        response = client.post(self.url, {
            "expected_version": "5",
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        })
        self.assertEqual(response.status_code, 302)
        reader.assert_called_once()
