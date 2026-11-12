"""Offline lifecycle regressions for the *operator-only* single-use research worker.

No real DNS, HTTP, robots or paid API traffic is allowed in CI. A positive
success is injected as *metadata*, and the existing network adapter is
separately exercised with synthetic HTML and robots responses.
"""
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app.clubs.models import Club, Country, League

from .manual_source_import import register_manual_official_source
from .dossier_versions import fork_dossier
from .models import (
    Evidence, Fact, FactDossier, FactReview,
    OfficialResearchPage, OfficialResearchRequest,
    ProductionJob, SourceReference,
)
from .one_time_research_worker import (
    ResearchRunRejected, _claim, _finish_failure,
    execute_one_time_research,
)
from .research_consents import (
    cancel_one_time_research_consent, record_one_time_research_consent,
)
from .safe_official_fetch import WebsiteFetchError


_BASIS = (
    "I inspected the club's official navigation, history section and "
    "identity before approving this domain."
)


class OneTimeWorkerTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="worker-owner@example.org", password="Only-For-Worker-Tests-2026",
        )
        self.other = User.objects.create_user(
            email="worker-other@example.org", password="Only-For-Worker-Tests-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, title="History of Sturm Graz",
            country_code="AT", league_name="Austrian Bundesliga", club_name="Sturm Graz",
        )
        self.dossier = register_manual_official_source(
            owner=self.owner, job_id=self.job.pk, expected_version=0,
            url="https://club.example.org/history",
            title="Official club history", context="club", basis=_BASIS,
            identity_confirmed=True, terms_confirmed=True,
            access_confirmed=True,
        )
        self.source = self.dossier.sources.get()
        self.fact = Fact.objects.create(
            dossier=self.dossier, predicate="founded_year", value=1909,
            assertion_text="The club was founded in 1909.",
        )
        self.request, _ = record_one_time_research_consent(
            owner=self.owner, job_id=self.job.pk,
            source_id=self.source.pk, expected_version=1,
            request_key=uuid4(), domain_rechecked=True,
            terms_rechecked=True, one_time_approved=True,
        )

    def execute(self, **changes):
        kwargs = {
            "owner_id": self.owner.pk,
            "job_id": self.job.pk,
            "request_id": self.request.pk,
        }
        kwargs.update(changes)
        return execute_one_time_research(**kwargs)

    def snapshot(self, subpages=2, *, context="club"):
        now = timezone.now().isoformat()
        pages = [{
            "url": self.source.url, "title": "Sturm Graz Official Website",
            "headings": ["Club history"], "retrieved_at": now,
            "verification_state": "unverified",
        }]
        for i in range(subpages):
            pages.append({
                "url": f"https://club.example.org/{'history' if context == 'club' else 'standings'}/{i}",
                "title": f"Season outline {i}",
                "headings": ["Outline", f"Section {i}"],
                "retrieved_at": now, "verification_state": "unverified",
                "category": "history" if context == "club" else "standings",
            })
        return {
            "job_id": self.job.pk, "club_id": self.job.club_id,
            "league_id": self.job.club.league_id,
            "context": context, "site_url": self.source.url,
            "robots_url": "https://club.example.org/robots.txt",
            "pages": pages, "source_status": "unverified", "stored": False,
        }

    def assert_no_fetch(self, callback):
        with patch("app.production.one_time_research_worker.research_official_website") as crawl:
            callback()
            crawl.assert_not_called()

    def test_explicit_operator_command_requires_execute_flag(self):
        def without():
            with self.assertRaises(CommandError):
                call_command(
                    "run_official_research_request",
                    job_id=self.job.pk, request_id=self.request.pk,
                    owner_id=self.owner.pk, stdout=StringIO(),
                )
        self.assert_no_fetch(without)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "pending_worker")
        self.assertEqual(self.request.attempt_count, 0)

    @patch("app.production.one_time_research_worker.research_official_website")
    def test_success_imports_only_unverified_page_outlines_into_new_dossier(self, research):
        research.return_value = self.snapshot()
        result = self.execute()
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["dossier_version"], 2)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "succeeded")
        self.assertEqual(self.request.attempt_count, 1)
        self.assertIsNotNone(self.request.finished_at)
        self.assertIsNone(self.request.lease_key)
        self.assertEqual(self.request.result_count, 3)
        self.assertEqual(self.request.result_dossier_version, 2)

        latest = FactDossier.objects.get(job=self.job, version=2)
        self.assertEqual(latest.sources.count(), 3)
        self.assertEqual(self.dossier.sources.count(), 1)
        self.assertEqual(latest.facts.count(), 1)
        self.assertEqual(latest.facts.get().verification_state, "unverified")
        self.assertEqual(self.fact.verification_state, "unverified")
        self.assertEqual(latest.sources.filter(
            source_kind="club_official", access_state="accessible",
        ).count(), 3)
        self.assertEqual(latest.sources.filter(
            manual_confirmation__isnull=False,
        ).count(), 1)
        self.assertEqual(OfficialResearchPage.objects.count(), 3)
        pages = list(self.request.pages.all())
        self.assertEqual([x.position for x in pages], [0, 1, 2])
        self.assertEqual([x.verification_state for x in pages], ["unverified"] * 3)
        self.assertEqual(pages[0].headings, ["Club history"])
        self.assertEqual(pages[0].saved_source.url, self.source.url)
        self.assertEqual(pages[0].saved_source.dossier_id, latest.pk)
        self.assertEqual(pages[1].saved_source.dossier_id, latest.pk)
        self.assertFalse(FactReview.objects.exists())
        self.assertFalse(Evidence.objects.exists())
        research.assert_called_once()
        self.assertEqual(research.call_args.kwargs["homepage_url"], self.source.url)
        self.assertTrue(callable(research.call_args.kwargs["continue_check"]))
        self.assertIsNotNone(research.call_args.kwargs["deadline"])

    @patch("app.production.one_time_research_worker.research_official_website")
    def test_robots_and_https_adapter_can_run_with_synthetic_guarded_pages(self, research):
        # The worker must use the existing strict helper: production tests for
        # this helper cover TLS pinning, DNS, redirect, 403/429, robots and size.
        research.side_effect = WebsiteFetchError("robots_disallowed")
        result = self.execute()
        self.assertEqual(result, {
            "status": "stopped", "request_id": self.request.pk,
            "code": "robots_disallowed",
        })
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "blocked")
        self.assertEqual(self.request.failure_code, "robots_disallowed")
        self.assertEqual(self.request.attempt_count, 1)
        self.assertEqual(FactDossier.objects.count(), 1)
        self.assertFalse(OfficialResearchPage.objects.exists())

    @patch("app.production.official_site_research.time.sleep")
    @patch("app.production.official_site_research._download_public_https")
    def test_worker_uses_real_robots_gate_and_safe_page_discovery_offline(
        self, download, sleep,
    ):
        # This exercises the actual robots gate + discovery path with an
        # artificial transport. No DNS, network or real website is contacted.
        download.side_effect = [
            "User-agent: *\nDisallow: /tickets\nCrawl-delay: 2\n",
            '<title>Sturm Graz History</title><h1>Club History</h1>'
            '<a href="/honours">Honours</a><a href="/tickets">Tickets</a>',
            '<title>Honours</title><h2>Titles</h2>',
        ]
        result = self.execute()
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(download.call_count, 3)  # robots, homepage, honours
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(OfficialResearchPage.objects.count(), 2)
        self.assertEqual(
            OfficialResearchPage.objects.get(position=1).url,
            "https://club.example.org/honours",
        )
        self.assertEqual(
            OfficialResearchPage.objects.get(position=1).verification_state,
            "unverified",
        )

    @patch("app.production.official_site_research.time.sleep")
    @patch("app.production.official_site_research._download_public_https")
    def test_existing_robots_disallow_blocks_before_homepage(
        self, download, sleep,
    ):
        download.return_value = "User-agent: *\nDisallow: /\n"
        result = self.execute()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["code"], "robots_disallowed")
        download.assert_called_once()
        sleep.assert_not_called()
        self.assertFalse(OfficialResearchPage.objects.exists())
        self.assertEqual(self.request.pages.count(), 0)

    @patch("app.production.one_time_research_worker.research_official_website")
    def test_operator_command_succeeds_without_ever_accepting_a_url(self, research):
        research.return_value = self.snapshot(0)
        output = StringIO()
        call_command(
            "run_official_research_request",
            job_id=self.job.pk, request_id=self.request.pk,
            owner_id=self.owner.pk, execute=True, stdout=output,
        )
        self.assertIn("Unverified metadata stored", output.getvalue())
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "succeeded")
        self.assertEqual(self.request.result_count, 1)

    @patch("app.production.one_time_research_worker.research_official_website")
    def test_identical_execution_never_calls_network_twice(self, research):
        research.return_value = self.snapshot(0)
        self.assertEqual(self.execute()["status"], "succeeded")
        with self.assertRaises(ResearchRunRejected):
            self.execute()
        self.assertEqual(research.call_count, 1)
        self.assertEqual(FactDossier.objects.count(), 2)

    def test_foreign_owner_or_incorrect_job_never_consumes_consent(self):
        for changes in (
            {"owner_id": self.other.pk},
            {"job_id": self.job.pk + 100},
            {"request_id": 99999999},
        ):
            with self.subTest(changes=changes):
                self.assert_no_fetch(
                    lambda: self.assertRaises(
                        ResearchRunRejected, self.execute, **changes,
                    )
                )
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "pending_worker")
        self.assertEqual(self.request.attempt_count, 0)

    def test_expired_unstarted_consent_is_terminal_not_refreshed(self):
        old_consent = timezone.now() - timedelta(minutes=25)
        OfficialResearchRequest.objects.filter(pk=self.request.pk).update(
            consented_at=old_consent,
            expires_at=old_consent + timedelta(minutes=15),
        )
        with self.assertRaises(ResearchRunRejected) as exc:
            self.assert_no_fetch(self.execute)
        self.assertEqual(str(exc.exception), "consent_expired")
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "expired")
        self.assertEqual(self.request.attempt_count, 0)

    def test_stale_dossier_blocks_without_even_claiming_network(self):
        fork_dossier(job=self.job, previous=self.dossier)
        with self.assertRaises(ResearchRunRejected):
            self.assert_no_fetch(self.execute)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "blocked")
        self.assertEqual(self.request.failure_code, "source_changed")
        self.assertEqual(self.request.attempt_count, 0)

    def test_owner_cancelled_consent_is_terminal_without_fetch(self):
        cancel_one_time_research_consent(
            owner=self.owner, job_id=self.job.pk,
            request_id=self.request.pk,
        )
        with self.assertRaises(ResearchRunRejected):
            self.assert_no_fetch(self.execute)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "cancelled")
        self.assertFalse(OfficialResearchPage.objects.exists())

    @patch("app.production.one_time_research_worker.research_official_website")
    def test_cancellation_during_running_stops_at_next_checkpoint(self, research):
        def interrupt(**kwargs):
            cancel_one_time_research_consent(
                owner=self.owner, job_id=self.job.pk, request_id=self.request.pk,
            )
            kwargs["continue_check"]()
            return self.snapshot()
        research.side_effect = interrupt
        result = self.execute()
        self.assertEqual(result["status"], "stopped")
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "cancelled")
        self.assertEqual(self.request.attempt_count, 1)
        self.assertEqual(FactDossier.objects.count(), 1)
        self.assertFalse(OfficialResearchPage.objects.exists())

    @patch("app.production.one_time_research_worker.research_official_website")
    def test_second_worker_cannot_claim_same_running_lease(self, research):
        def concurrent(**kwargs):
            with self.assertRaises(ResearchRunRejected):
                self.execute()
            return self.snapshot(0)
        research.side_effect = concurrent
        result = self.execute()
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(research.call_count, 1)
        self.assertEqual(self.request.pages.count(), 1)

    def test_crashed_running_lease_is_failed_without_reexecution(self):
        pk, token, *_ = _claim(
            owner_id=self.owner.pk, job_id=self.job.pk, request_id=self.request.pk,
        )
        OfficialResearchRequest.objects.filter(pk=pk).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1),
        )
        with self.assertRaises(ResearchRunRejected):
            self.assert_no_fetch(self.execute)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "failed")
        self.assertEqual(self.request.failure_code, "worker_lease_expired")
        self.assertEqual(self.request.attempt_count, 1)
        self.assertFalse(self.request.pages.exists())

    @patch("app.production.one_time_research_worker.research_official_website")
    def test_dossier_edit_during_crawl_discards_all_results(self, research):
        def alter(**kwargs):
            fork_dossier(job=self.job, previous=self.dossier)
            return self.snapshot()
        research.side_effect = alter
        result = self.execute()
        self.assertEqual(result["status"], "stopped")
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "failed")
        self.assertEqual(result["code"], "research_cancelled")
        self.assertEqual(FactDossier.objects.count(), 2)
        self.assertEqual(OfficialResearchPage.objects.count(), 0)

    def _assert_rejected_snapshot(self, pages):
        with patch(
            "app.production.one_time_research_worker.research_official_website",
            return_value=pages,
        ):
            result = self.execute()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(FactDossier.objects.count(), 1)
        self.assertEqual(OfficialResearchPage.objects.count(), 0)
        self.request.refresh_from_db()
        self.assertIn(self.request.status, ("failed", "blocked"))

    def test_foreign_domain_in_snapshot_is_not_imported(self):
        pages = self.snapshot(1)
        pages["pages"][1]["url"] = "https://evil.example.org/secret"
        self._assert_rejected_snapshot(pages)

    def test_five_page_snapshot_is_rejected(self):
        self._assert_rejected_snapshot(self.snapshot(4))

    def test_attempt_to_mark_page_verified_is_rejected(self):
        pages = self.snapshot(1)
        pages["pages"][1]["verification_state"] = "verified"
        self._assert_rejected_snapshot(pages)

    def test_oversized_heading_is_rejected(self):
        pages = self.snapshot(1)
        pages["pages"][1]["headings"] = ["x" * 300]
        self._assert_rejected_snapshot(pages)

    def test_db_constraints_reject_verified_pages_and_extra_attempts(self):
        OfficialResearchRequest.objects.filter(pk=self.request.pk).update(
            status="succeeded",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                # bulk_create bypasses model.clean and verifies the
                # database constraint itself rejects a forged review state.
                OfficialResearchPage.objects.bulk_create([
                    OfficialResearchPage(
                        request=self.request, position=0, url=self.source.url,
                        title="Safe", headings=[], retrieved_at=timezone.now(),
                        verification_state="verified",
                    )
                ])
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OfficialResearchRequest.objects.filter(pk=self.request.pk).update(
                    attempt_count=2,
                )

    @patch("app.production.one_time_research_worker.research_official_website")
    def test_dossier_version_rate_limit_rejects_atomic_result_commit(self, research):
        # Prepare a fresh valid consent against the 10th recent dossier,
        # so the result-write throttle (rather than staleness) is exercised.
        self.request.delete()
        current = self.dossier
        for _ in range(9):
            current = fork_dossier(job=self.job, previous=current)
        current_source = current.sources.get(url=self.source.url)
        self.request, _ = record_one_time_research_consent(
            owner=self.owner, job_id=self.job.pk,
            source_id=current_source.pk, expected_version=10,
            request_key=uuid4(), domain_rechecked=True,
            terms_rechecked=True, one_time_approved=True,
        )
        research.return_value = self.snapshot(1)
        response = self.execute()
        self.assertEqual(response["status"], "stopped")
        self.assertEqual(response["code"], "version_rate_limited")
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "failed")
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 10)
        self.assertEqual(OfficialResearchPage.objects.count(), 0)

    @patch("app.production.one_time_research_worker.research_official_website")
    def test_failed_upstream_safe_error_does_not_expose_article_or_stack(self, research):
        research.side_effect = RuntimeError("SECRET article body and internal URL")
        result = self.execute()
        self.assertEqual(result["code"], "worker_error")
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "failed")
        self.assertEqual(self.request.failure_code, "worker_error")
        self.assertNotIn("SECRET", str(self.request.failure_code))
        self.assertFalse(OfficialResearchPage.objects.exists())

    @patch("app.production.one_time_research_worker.research_official_website")
    def test_private_status_html_never_triggers_site_requests(self, research):
        research.return_value = self.snapshot(1)
        self.execute()
        self.client.force_login(self.owner)
        url = reverse("research-requests", kwargs={"job_id": self.job.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Abgeschlossen")
        self.assertContains(response, "Sturm Graz Official Website")
        self.assertContains(response, "Ungeprüfte Seitenreferenz")
        self.assertNotContains(response, "Keine Freigabe wurde ausgeführt")
        self.assertEqual(research.call_count, 1)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(research.call_count, 1)
