"""FS-017: persistent worker safety / recovery, no fake renderer or reviews."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from app.clubs.models import Club, Country, League
from .film_worker import (
    claim_queued_film_job, perform_film_research, recover_stale_film_jobs,
    run_film_worker_once,
)
from .models import (
    FactDossier, PaidApiCharge, ProductionJob, SourceReference,
)
from .wikimedia_auto import AutoResearchError


class FilmWorkerTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="film-worker@example.test", password="only-test-password-1234",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.film = ProductionJob.objects.create(
            owner=self.owner, club=club, club_name=club.name,
            league_name=league.name, country_code=country.code,
            title="The Story of Sturm Graz",
            kind=ProductionJob.Kind.FILM, status=ProductionJob.Status.QUEUED,
        )
        self.proto = ProductionJob.objects.create(
            owner=self.owner, club=club, club_name=club.name,
            league_name=league.name, country_code=country.code,
            title="Old Test",
            kind=ProductionJob.Kind.PROTOTYPE,
            status=ProductionJob.Status.QUEUED,
        )

    def test_only_film_claimed_and_second_call_does_not_duplicate(self):
        claimed = claim_queued_film_job()
        self.assertEqual(claimed, self.film.pk)
        self.film.refresh_from_db()
        self.assertEqual(self.film.status, "running")
        self.assertIsNone(claim_queued_film_job())
        self.proto.refresh_from_db()
        self.assertEqual(self.proto.status, "queued")

    @patch("app.production.film_worker.perform_film_research")
    def test_once_claims_only_one_and_enters_own_runner(self, perform):
        self.assertEqual(run_film_worker_once(), self.film.pk)
        perform.assert_called_once_with(self.film.pk)
        self.assertIsNone(run_film_worker_once())

    @patch("app.production.official_source_candidates.import_official_site_candidates")
    @patch("app.production.wikimedia_players.import_wikidata_player_candidates")
    @patch("app.production.wikimedia_stadium.enrich_wikimedia_stadium")
    @patch("app.production.wikimedia_auto.import_free_club_research")
    def test_auto_research_skips_optional_failures_without_user_clicks(
        self, discover, stadium, players, sites,
    ):
        self.film.transition_to(ProductionJob.Status.RUNNING)

        def seed_identity(**kwargs):
            self.assertEqual(kwargs["job_id"], self.film.pk)
            self.assertEqual(kwargs["expected_version"], 0)
            dossier = FactDossier.objects.create(job=self.film, version=1)
            SourceReference.objects.create(
                dossier=dossier,
                source_kind="wikidata",
                url=("https://www.wikidata.org/wiki/Special:EntityData/"
                     "Q124007617.json"),
                title="[auto] SK Sturm Graz",
                external_id="Q124007617",
                retrieved_at=timezone.now(), access_state="accessible",
            )
            return dossier

        discover.side_effect = seed_identity
        stadium.side_effect = AutoResearchError("no_stadium_candidate")
        players.side_effect = AutoResearchError("no_people_candidates")
        sites.side_effect = AutoResearchError("network_error")
        perform_film_research(self.film.pk)
        self.film.refresh_from_db()
        self.assertEqual(self.film.status, ProductionJob.Status.FAILED)
        self.assertIn("MP4", self.film.error_message)
        self.assertFalse(self.film.output_path)
        discover.assert_called_once()
        stadium.assert_called_once()
        players.assert_called_once()
        sites.assert_called_once()
        self.assertFalse(PaidApiCharge.objects.exists())
        self.assertEqual(FactDossier.objects.filter(job=self.film).count(), 1)
        self.assertEqual(self.proto.status, ProductionJob.Status.QUEUED)

    @patch("app.production.wikimedia_auto.import_free_club_research")
    def test_ambiguous_club_stops_without_fake_video(self, discover):
        self.film.transition_to(ProductionJob.Status.RUNNING)
        discover.side_effect = AutoResearchError("no_confident_match")
        perform_film_research(self.film.pk)
        self.film.refresh_from_db()
        self.assertEqual(self.film.status, ProductionJob.Status.FAILED)
        self.assertIn("Vereinszuordnung", self.film.error_message)
        self.assertEqual(self.film.output_path, "")
        self.assertEqual(FactDossier.objects.filter(job=self.film).count(), 0)
        self.assertFalse(PaidApiCharge.objects.exists())

    @patch("app.production.wikimedia_auto.import_free_club_research")
    def test_unexpected_exception_sets_safe_failure_without_leaking_upstream(
        self, discover,
    ):
        self.film.transition_to(ProductionJob.Status.RUNNING)
        discover.side_effect = RuntimeError("secret upstream token should not leak")
        perform_film_research(self.film.pk)
        self.film.refresh_from_db()
        self.assertEqual(self.film.status, ProductionJob.Status.FAILED)
        self.assertNotIn("secret", self.film.error_message)
        self.assertFalse(self.film.output_path)

    def test_stale_worker_job_is_requeued_but_active_job_not_stolen(self):
        self.film.transition_to(ProductionJob.Status.RUNNING)
        ProductionJob.objects.filter(pk=self.film.pk).update(
            updated_at=timezone.now() - timedelta(minutes=90)
        )
        self.assertEqual(recover_stale_film_jobs(), 1)
        self.film.refresh_from_db()
        self.assertEqual(self.film.status, ProductionJob.Status.QUEUED)
        self.assertEqual(recover_stale_film_jobs(), 0)
        self.assertEqual(ProductionJob.objects.filter(kind="prototype").count(), 1)

    def test_recent_running_job_not_reclaimed(self):
        self.film.transition_to(ProductionJob.Status.RUNNING)
        self.assertEqual(recover_stale_film_jobs(), 0)
        self.film.refresh_from_db()
        self.assertEqual(self.film.status, ProductionJob.Status.RUNNING)
