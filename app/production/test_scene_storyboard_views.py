"""Owner-only storyboard UI: GET preview, explicit CSRF POST save, safe reload."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from app.clubs.models import Club, Country, League

from .fact_reviews import decide_fact_review
from .models import (
    Evidence, Fact, FactDossier, ProductionJob, ScenePlanSnapshot,
    SourceReference,
)


_NOTE = (
    "I checked the original club history page and the foundation "
    "chronology supports this specific founding year."
)


class SceneStoryBoardWebTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="storyboard-owner@example.org",
            password="Local-test-only-password-2026",
        )
        self.other = User.objects.create_user(
            email="storyboard-other@example.org",
            password="Local-test-only-password-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Example League")
        club = Club.objects.create(league=league, name="Example FC")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, country_code="AT",
            league_name="Example League", club_name="Example FC",
            title="An Example Football Club Documentary",
        )
        self.base = reverse(
            "research-scene-plan", kwargs={"job_id": self.job.pk},
        )
        dossier = FactDossier.objects.create(job=self.job, version=1)
        source = SourceReference.objects.create(
            dossier=dossier, source_kind="club_official",
            url="https://club.example.org/history",
            title="Official club history",
            retrieved_at=timezone.now(), access_state="accessible",
        )
        fact = Fact.objects.create(
            dossier=dossier, predicate="founded_year", value=1909,
            assertion_text="The club was founded in 1909.",
        )
        Evidence.objects.create(
            fact=fact, source=source, role="supports",
            locator="Chronology > Foundation 1909",
            summary="The official chronology names the founding year as 1909.",
        )
        self.client.force_login(self.owner)
        self.fact_id = fact.pk

    def review_fact(self):
        return decide_fact_review(
            owner=self.owner, job_id=self.job.pk, expected_version=1,
            fact_id=self.fact_id, decision="verified",
            review_note=_NOTE, review_confirmed=True,
            source_checked=True,
        )

    def form_payload(self, response, *, version=2, wpm=145):
        return {
            "version": str(version),
            "wpm": str(wpm),
            "expected_fingerprint":
                response.context["plan"]["plan_fingerprint_sha256"],
        }

    def test_unreviewed_dossier_cannot_be_saved(self):
        response = self.client.get(self.base)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Noch keine geeigneten")
        self.assertNotContains(response, "Diesen Szenenplan jetzt speichern")
        self.assertEqual(ScenePlanSnapshot.objects.count(), 0)
        self.assertIn("no-store", response["Cache-Control"])
        attempt = self.client.post(self.base, {
            "version": "1", "wpm": "145",
            "expected_fingerprint": "0" * 64,
        })
        self.assertEqual(attempt.status_code, 409)
        self.assertEqual(ScenePlanSnapshot.objects.count(), 0)

    def test_user_opens_saves_and_reloads_real_reviewed_dossier(self):
        self.review_fact()
        overview = self.client.get(reverse(
            "research-job", kwargs={"job_id": self.job.pk},
        ) + "?version=2")
        self.assertContains(overview, self.base + "?version=2")

        before = self.client.get(self.base + "?version=2")
        self.assertEqual(before.status_code, 200)
        self.assertContains(before, "The club was founded in 1909.")
        self.assertContains(before, "Originalquelle öffnen")
        self.assertContains(before, "Medienrechte nicht freigegeben")
        self.assertContains(before, "Diesen Szenenplan jetzt speichern")
        self.assertContains(before, "Zu kurz für 8–10 Minuten")
        self.assertEqual(ScenePlanSnapshot.objects.count(), 0)

        result = self.client.post(self.base, self.form_payload(before))
        self.assertEqual(result.status_code, 302)
        self.assertIn("version=2", result["Location"])
        self.assertEqual(ScenePlanSnapshot.objects.count(), 1)
        saved = self.client.get(result["Location"])
        self.assertContains(saved, "Version gespeichert")
        self.assertNotContains(saved, "Diesen Szenenplan jetzt speichern")
        self.assertEqual(len(saved.context["scene_cards"]), 3)
        self.assertFalse(saved.context["plan"]["ready_for_tts"])
        self.assertFalse(saved.context["plan"]["ready_for_render"])
        self.assertEqual(ScenePlanSnapshot.objects.count(), 1)
        self.assertIn("no-store", saved["Cache-Control"])

    def test_get_and_historical_views_never_write(self):
        self.review_fact()
        for path in (
            self.base,
            self.base + "?version=2",
            self.base + "?version=1",
            self.base + "?version=2&wpm=120",
            self.base + "?version=2&wpm=165",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(ScenePlanSnapshot.objects.count(), 0)
        historical = self.client.get(self.base + "?version=1")
        self.assertContains(historical, "Noch keine sichere Szenenplanung")
        self.assertEqual(self.client.post(self.base, {
            "version": "1", "wpm": "145",
            "expected_fingerprint": "0" * 64,
        }).status_code, 409)

    def test_old_preview_cannot_save_changed_title(self):
        self.review_fact()
        response = self.client.get(self.base + "?version=2")
        payload = self.form_payload(response)
        self.job.title = "Title now changed"
        self.job.save(update_fields=["title", "updated_at"])
        stale = self.client.post(self.base, payload)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(ScenePlanSnapshot.objects.count(), 0)

    def test_invalid_fingerprint_is_rejected_without_write(self):
        self.review_fact()
        response = self.client.get(self.base)
        for wrong in ("", "bad", "0" * 64, "a" * 999):
            payload = self.form_payload(response)
            payload["expected_fingerprint"] = wrong
            with self.subTest(wrong=wrong[:10]):
                self.assertEqual(self.client.post(self.base, payload).status_code, 409)
        self.assertEqual(ScenePlanSnapshot.objects.count(), 0)

    def test_malformed_versions_and_rates_are_rejected(self):
        self.review_fact()
        for query in (
            "?version=0", "?version=999", "?version=02",
            "?version=<script>", "?wpm=99", "?wpm=201",
            "?wpm=145.0", "?wpm=0", "?wpm=999999",
        ):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(self.base + query).status_code, 404)
        self.assertEqual(ScenePlanSnapshot.objects.count(), 0)

    def test_no_dossier_returns_404(self):
        orphan = ProductionJob.objects.create(
            owner=self.owner, club=self.job.club,
            country_code="AT", league_name="Example League",
            club_name="Example FC", title="Another test project",
        )
        self.assertEqual(self.client.get(reverse(
            "research-scene-plan", kwargs={"job_id": orphan.pk},
        )).status_code, 404)

    def test_other_owner_get_and_post_are_inaccessible(self):
        self.review_fact()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.base).status_code, 404)
        self.assertEqual(self.client.post(self.base, {
            "version": "2", "wpm": "145",
            "expected_fingerprint": "0" * 64,
        }).status_code, 404)
        self.assertEqual(ScenePlanSnapshot.objects.count(), 0)

    def test_anonymous_user_redirected_to_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.base).status_code, 302)
        self.assertEqual(self.client.post(self.base).status_code, 302)

    def test_stale_saved_plan_is_not_offered_as_current(self):
        self.review_fact()
        response = self.client.get(self.base)
        self.client.post(self.base, self.form_payload(response))
        self.job.title = "New working title after snapshot"
        self.job.save(update_fields=["title", "updated_at"])
        stale = self.client.get(self.base)
        self.assertContains(stale, "Der gespeicherte Plan ist veraltet")
        self.assertNotContains(stale, "Diesen Szenenplan jetzt speichern")
        self.assertNotContains(stale, "Version gespeichert")
        self.assertEqual(ScenePlanSnapshot.objects.count(), 1)

    def test_csrf_mandatory_for_explicit_save(self):
        self.review_fact()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        preview = client.get(self.base)
        payload = self.form_payload(preview)
        self.assertEqual(client.post(self.base, payload).status_code, 403)
        self.assertEqual(ScenePlanSnapshot.objects.count(), 0)
        payload["csrfmiddlewaretoken"] = client.cookies["csrftoken"].value
        accepted = client.post(self.base, payload)
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(ScenePlanSnapshot.objects.count(), 1)

    @patch("socket.getaddrinfo")
    @patch("urllib.request.urlopen")
    def test_preview_and_save_make_no_network_requests(self, http, dns):
        self.review_fact()
        preview = self.client.get(self.base)
        self.client.post(self.base, self.form_payload(preview))
        self.client.get(self.base)
        dns.assert_not_called()
        http.assert_not_called()
