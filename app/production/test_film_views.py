"""FS-017: one-click film queue, owner privacy and honest status UI tests."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from app.clubs.models import Club, Country, League
from .models import ProductionJob


class OneClickFilmViewsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="film-request@example.test", password="test-password-12345",
        )
        self.other = User.objects.create_user(
            email="film-request-other@example.test", password="test-password-12345",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(
            country=country, name="Austrian Bundesliga",
        )
        self.club = Club.objects.create(league=league, name="Sturm Graz")
        self.data = {
            "country": "AT", "league": str(league.pk), "club": str(self.club.pk),
        }
        self.create = reverse("production:create-film")
        self.client.force_login(self.owner)

    def test_one_click_creates_queued_film_without_title_or_manual_source(self):
        response = self.client.post(self.create, self.data)
        self.assertEqual(response.status_code, 201)
        film = ProductionJob.objects.get()
        self.assertEqual(film.kind, ProductionJob.Kind.FILM)
        self.assertEqual(film.status, ProductionJob.Status.QUEUED)
        self.assertEqual(film.title, "The Story of Sturm Graz")
        self.assertEqual(film.language, "en")
        self.assertFalse(film.output_path)
        self.assertFalse(response.json()["job"]["video_ready"])
        self.assertEqual(response.json()["job"]["phase"], "queued")
        self.assertEqual(response.json()["job"]["research_total"], 6)
        page = self.client.get(reverse("film-status-page", kwargs={"job_id": film.pk}))
        self.assertContains(page, "Video erstellen")
        self.assertContains(page, "Quellen und Recherche optional ansehen")
        self.assertContains(page, "Diese Seite darf geschlossen werden")
        self.assertEqual(ProductionJob.objects.count(), 1)

    def test_double_click_is_idempotent_for_same_club_while_queued(self):
        first = self.client.post(self.create, self.data)
        again = self.client.post(self.create, self.data)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.json()["created"])
        self.assertEqual(first.json()["job"]["id"], again.json()["job"]["id"])
        self.assertEqual(ProductionJob.objects.count(), 1)

    def test_invalid_selection_and_get_are_rejected_without_jobs(self):
        self.assertEqual(self.client.get(self.create).status_code, 405)
        for bad in (
            {"country": "AT", "league": "0", "club": str(self.club.pk)},
            {"country": "DE", "league": self.data["league"], "club": self.data["club"]},
            {"country": "AT", "league": "123456", "club": self.data["club"]},
            {"country": "AT", "league": self.data["league"], "club": "999999"},
            {"country": "AT", "league": self.data["league"], "club": "true"},
        ):
            with self.subTest(bad=bad):
                result = self.client.post(self.create, bad)
                self.assertIn(result.status_code, (400, 404))
        self.assertFalse(ProductionJob.objects.exists())

    def test_private_page_and_json_are_owner_scoped(self):
        film_id = self.client.post(self.create, self.data).json()["job"]["id"]
        page = reverse("film-status-page", kwargs={"job_id": film_id})
        status = reverse("production:film-status", kwargs={"job_id": film_id})
        self.assertEqual(self.client.get(page).status_code, 200)
        self.assertEqual(self.client.get(status).json()["job"]["id"], film_id)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(page).status_code, 404)
        self.assertEqual(self.client.get(status).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(page).status_code, 302)
        self.assertEqual(self.client.get(status).status_code, 302)

    def test_csrf_blocks_one_click_start(self):
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.owner)
        self.assertEqual(secure.post(self.create, self.data).status_code, 403)
        self.assertFalse(ProductionJob.objects.exists())
        secure.get(reverse("home"))
        csrf = secure.cookies["csrftoken"].value
        response = secure.post(self.create, {
            **self.data, "csrfmiddlewaretoken": csrf,
        })
        self.assertEqual(response.status_code, 201)

    def test_home_exposes_primary_video_start_and_optional_test_form(self):
        home = self.client.get(reverse("home"))
        self.assertContains(home, "Video erstellen")
        self.assertContains(home, 'id="film-form"')
        self.assertContains(home, "Erweiterte Testwerkzeuge (optional)")
        self.assertContains(home, "lizenzierte Medien")
        self.assertContains(home, 'filmForm.addEventListener("submit"')

    def test_failed_film_is_not_false_success_or_download_link(self):
        film_id = self.client.post(self.create, self.data).json()["job"]["id"]
        film = ProductionJob.objects.get(pk=film_id)
        film.transition_to(ProductionJob.Status.RUNNING)
        film.transition_to(
            ProductionJob.Status.FAILED,
            error_message="Noch keine MP4: Der Renderer ist nicht implementiert.",
        )
        status = self.client.get(
            reverse("production:film-status", kwargs={"job_id": film_id}),
        ).json()["job"]
        self.assertFalse(status["video_ready"])
        self.assertEqual(status["phase"], "needs_pipeline")
        page = self.client.get(
            reverse("film-status-page", kwargs={"job_id": film_id}),
        )
        self.assertContains(page, "Noch keine MP4")
        self.assertNotContains(page, "Video ist fertig")
        self.assertNotContains(page, "http-equiv=\"refresh\"")
