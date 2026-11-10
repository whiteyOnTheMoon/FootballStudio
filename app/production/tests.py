"""Production-job state machine, ownership, M1 selection and API security tests."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse

from app.clubs.catalog import season_label, season_start
from app.clubs.models import Club, Country, League

from .models import ProductionJob


class PrototypeJobTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="job-owner@example.com", password="M1-secure-passphrase!"
        )
        self.other = User.objects.create_user(
            email="not-owner@example.com", password="Other-secure-passphrase!"
        )
        self.client.force_login(self.owner)
        self.country = Country.objects.create(code="GB", name="England (UK)")
        self.league = League.objects.create(
            country=self.country, name="Premier League", tier=1,
            provider="openfootball", provider_id="en.1",
            catalog_season=season_label(season_start()),
        )
        self.club = Club.objects.create(
            league=self.league, name="Example FC", provider="openfootball",
            provider_id="example-001", is_manual=False,
        )
        self.second = Club.objects.create(
            league=self.league, name="Town AFC", provider="manual",
            provider_id="", is_manual=True,
        )
        self.de = Country.objects.create(code="DE", name="Deutschland")
        self.german = League.objects.create(
            country=self.de, name="Bundesliga", tier=1,
            provider="openligadb", provider_id="bl1",
            catalog_season=season_label(season_start()),
        )
        self.create_url = reverse("production:create-test")
        self.list_url = reverse("production:list")

    def payload(self, club=None, league=None, country="GB", title="The Rise of a Club"):
        selected = club or self.club
        return {
            "country": country, "league": (league or self.league).pk,
            "club": selected.pk, "title": title,
        }

    def create(self, **kwargs):
        return self.client.post(self.create_url, self.payload(**kwargs))

    def test_selected_club_and_title_saved_without_rendering(self):
        r = self.create(title="  A Legacy   in Football  ")
        self.assertEqual(r.status_code, 201)
        job = ProductionJob.objects.get()
        self.assertEqual(job.owner, self.owner)
        self.assertEqual(job.club, self.club)
        self.assertEqual(job.country_code, "GB")
        self.assertEqual(job.league_name, "Premier League")
        self.assertEqual(job.club_name, "Example FC")
        self.assertEqual(job.title, "A Legacy in Football")
        self.assertEqual(job.language, "en")
        self.assertEqual(job.kind, ProductionJob.Kind.PROTOTYPE)
        self.assertEqual(job.status, ProductionJob.Status.QUEUED)
        self.assertFalse(job.output_path)
        self.assertIsNone(job.started_at)
        self.assertFalse(r.json()["job"]["has_video"])

    def test_manual_club_can_start_a_test_job(self):
        r = self.create(club=self.second, title="My Local Club Story")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(ProductionJob.objects.get().club, self.second)

    def test_rejects_cross_country_and_cross_league_club_forgery(self):
        for params in (
            self.payload(country="DE"),
            self.payload(league=self.german, country="DE"),
        ):
            with self.subTest(params=params):
                response = self.client.post(self.create_url, params)
                self.assertEqual(response.status_code, 404)
        self.assertFalse(ProductionJob.objects.exists())

    def test_rejects_inactive_club_or_league(self):
        self.club.is_active = False
        self.club.save()
        self.assertEqual(self.create().status_code, 404)
        self.club.is_active = True
        self.club.save()
        self.league.is_active = False
        self.league.save(update_fields=["is_active"])
        self.assertEqual(self.create().status_code, 404)

    def test_title_required_with_minimum_length(self):
        for title in ("", "A", "Abc", " " * 7, "X" * 181):
            with self.subTest(title=title[:9]):
                self.assertEqual(self.create(title=title).status_code, 400)
        self.assertFalse(ProductionJob.objects.exists())

    def test_only_owner_sees_their_jobs(self):
        r = self.create()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(self.client.get(self.list_url).json()["jobs"]), 1)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.list_url).json()["jobs"], [])

    def test_anonymous_or_get_cannot_create(self):
        self.assertEqual(self.client.get(self.create_url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(self.create_url, self.payload()).status_code, 302)
        self.assertEqual(self.client.get(self.list_url).status_code, 302)
        self.assertFalse(ProductionJob.objects.exists())

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(
            client.post(self.create_url, self.payload()).status_code, 403
        )
        self.assertFalse(ProductionJob.objects.exists())

    def test_snapshots_survive_club_name_change(self):
        self.create()
        job = ProductionJob.objects.get()
        self.club.name = "Renamed Example FC"
        self.club.save()
        job.refresh_from_db()
        self.assertEqual(job.club_name, "Example FC")
        self.assertEqual(job.club.name, "Renamed Example FC")

    def test_club_cannot_be_deleted_while_job_references_it(self):
        self.create()
        with self.assertRaises(ProtectedError):
            self.club.delete()

    def test_invalid_prototype_job_transition_is_rejected(self):
        self.create()
        job = ProductionJob.objects.get()
        with self.assertRaises(ValidationError):
            job.transition_to(ProductionJob.Status.RUNNING)
        job.refresh_from_db()
        self.assertEqual(job.status, ProductionJob.Status.QUEUED)
        with self.assertRaises(ValidationError):
            job.transition_to(ProductionJob.Status.FAILED)
        job.transition_to(ProductionJob.Status.FAILED, error_message="Demo error")
        job.refresh_from_db()
        self.assertEqual(job.status, ProductionJob.Status.FAILED)
        self.assertEqual(job.error_message, "Demo error")
        self.assertIsNotNone(job.finished_at)
        self.assertIn("Demo error", str(self.client.get(self.list_url).json()["jobs"]))
        job.transition_to(ProductionJob.Status.QUEUED)
        job.refresh_from_db()
        self.assertEqual(job.status, ProductionJob.Status.QUEUED)
        self.assertEqual(job.error_message, "")
        with self.assertRaises(ValidationError):
            job.transition_to(ProductionJob.Status.COMPLETED)

    def test_film_state_machine_requires_finished_output_reference(self):
        self.create()
        job = ProductionJob.objects.get()
        job.kind = ProductionJob.Kind.FILM
        job.save(update_fields=["kind"])
        job.transition_to(ProductionJob.Status.RUNNING)
        self.assertIsNotNone(job.started_at)
        with self.assertRaises(ValidationError):
            job.transition_to(ProductionJob.Status.COMPLETED)
        job.output_path = "production-data/jobs/demo/render/en/documentary.mp4"
        job.transition_to(ProductionJob.Status.COMPLETED)
        self.assertIsNotNone(job.finished_at)

    def test_no_paid_provider_or_background_worker_is_invoked(self):
        from unittest.mock import patch
        with patch("app.clubs.catalog.fetch_json") as network:
            response = self.create()
            self.assertEqual(response.status_code, 201)
            network.assert_not_called()
