"""DB, browser and CSRF tests: consent never executes a network operation."""
from datetime import timedelta
from uuid import UUID, uuid4
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from app.clubs.models import Club, Country, League

from .dossier_versions import fork_dossier
from .manual_source_import import register_manual_official_source
from .models import (
    Fact, FactDossier, OfficialResearchRequest, ProductionJob,
    SourceConfirmation, SourceReference,
)
from .research_consents import (
    ResearchConsentConflict, ResearchConsentInvalid,
    ResearchConsentRateLimited, ResearchConsentStale,
    cancel_one_time_research_consent, record_one_time_research_consent,
)


BASIS = (
    "I inspected the original official club menu and confirmed "
    "this site belongs to the selected football club."
)


class OneTimeResearchConsentWebTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="request-owner@example.org",
            password="Test-Only-One-Time-Consent-Owner-2026",
        )
        self.other = User.objects.create_user(
            email="request-other@example.org",
            password="Test-Only-One-Time-Consent-Other-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, title="Sturm Graz history",
            country_code="AT", league_name="Austrian Bundesliga",
            club_name="Sturm Graz",
        )
        self.other_job = ProductionJob.objects.create(
            owner=self.other, club=club, title="Other owner history",
            country_code="AT", league_name="Austrian Bundesliga",
            club_name="Sturm Graz",
        )
        self.dossier = register_manual_official_source(
            owner=self.owner, job_id=self.job.pk, expected_version=0,
            url="https://club.example.org/history", title="Official history",
            context="club", basis=BASIS,
            identity_confirmed=True, terms_confirmed=True,
            access_confirmed=True,
        )
        self.source = self.dossier.sources.get()
        self.url = reverse(
            "research-approve-source",
            kwargs={"job_id": self.job.pk, "source_id": self.source.pk},
        )
        self.list_url = reverse(
            "research-requests", kwargs={"job_id": self.job.pk},
        )
        self.preflight = reverse(
            "research-preflight", kwargs={"job_id": self.job.pk},
        )
        self.client.force_login(self.owner)

    def another_source(self, job=None, domain="league.example.org", context="league"):
        job = job or self.job
        last = FactDossier.objects.filter(job=job).order_by("-version").first()
        dossier = register_manual_official_source(
            owner=job.owner, job_id=job.pk,
            expected_version=last.version if last else 0,
            url=f"https://{domain}/about", title="Official page",
            context=context, basis=BASIS,
            identity_confirmed=True, terms_confirmed=True,
            access_confirmed=True,
        )
        return dossier.sources.get(url=f"https://{domain}/about")

    def payload(self, *, url=None, **changes):
        url = url or self.url
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        values = {
            "expected_version": str(page.context["dossier"].version),
            "request_key": str(page.context["form"].initial["request_key"]),
            "domain_rechecked": "on",
            "terms_rechecked": "on",
            "one_time_approved": "on",
        }
        values.update(changes)
        return values

    def approve(self, *, payload=None, url=None):
        return self.client.post(url or self.url, payload or self.payload(url=url))

    def only(self):
        return OfficialResearchRequest.objects.get(job=self.job)

    def cancel_url(self, record=None):
        record = record or self.only()
        return reverse(
            "research-cancel-request",
            kwargs={"job_id": self.job.pk, "request_id": record.pk},
        )

    def test_get_is_private_read_only_and_requires_three_new_confirmations(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Sturm Graz")
        self.assertContains(r, "15 Minuten")
        self.assertContains(r, self.source.url)
        self.assertContains(r, BASIS)
        self.assertContains(r, "https://club.example.org/robots.txt")
        self.assertContains(r, "erneut kontrolliert")
        self.assertContains(r, "aktuelle")
        self.assertContains(r, "KEIN Abruf")
        self.assertContains(r, 'name="csrfmiddlewaretoken"')
        for field in (
            "request_key", "expected_version", "domain_rechecked",
            "terms_rechecked", "one_time_approved",
        ):
            self.assertContains(r, f'name="{field}"')
        self.assertNotContains(r, 'name="url"')
        self.assertEqual(r.context["dossier"].version, 1)
        self.assertEqual(r.context["form"].initial["request_key"].version, 4)
        self.assertIn("no-store", r["Cache-Control"])
        self.assertFalse(OfficialResearchRequest.objects.exists())
        p = self.client.get(self.preflight, {"source_id": self.source.pk})
        self.assertContains(p, "Einmalige Freigabe für diese Quelle")
        self.assertContains(self.client.get(self.list_url),
                            "noch keine einmaligen Recherchefreigaben")

    def test_valid_post_persists_exact_audit_without_execution_or_facts(self):
        data = self.payload()
        response = self.approve(payload=data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{self.list_url}?request_id=1")
        record = self.only()
        self.assertEqual(record.source_id, self.source.pk)
        self.assertEqual(record.expected_version, 1)
        self.assertEqual(record.requested_by_id, self.owner.pk)
        self.assertEqual(record.job_id, self.job.pk)
        self.assertEqual(record.request_key, UUID(data["request_key"]))
        self.assertEqual(record.confirmed_url, self.source.url)
        self.assertEqual(record.confirmed_domain, "club.example.org")
        self.assertEqual(record.context, "club")
        self.assertTrue(record.domain_rechecked)
        self.assertTrue(record.terms_rechecked)
        self.assertTrue(record.one_time_approved)
        self.assertEqual(record.status, "pending_worker")
        self.assertEqual(record.visible_status, "pending_worker")
        self.assertEqual(record.attempt_count, 0)
        self.assertEqual(record.max_pages, 4)
        self.assertEqual(record.expires_at - record.consented_at, timedelta(minutes=15))
        self.assertFalse(Fact.objects.exists())
        self.assertEqual(FactDossier.objects.count(), 1)
        r = self.client.get(response.url)
        self.assertContains(r, "Erfasst · nicht ausgeführt")
        self.assertContains(r, "Netzwerkzugriffe:")
        self.assertContains(r, "0")
        self.assertContains(r, "abbrechen")
        self.assertNotContains(r, "recherchiert und gespeichert")

    def test_same_form_key_is_idempotent_and_new_form_conflicts_while_pending(self):
        data = self.payload()
        first = self.approve(payload=data)
        second = self.approve(payload=data)
        self.assertEqual((first.status_code, second.status_code), (302, 302))
        self.assertEqual(first.url, second.url)
        self.assertEqual(OfficialResearchRequest.objects.count(), 1)
        changed = self.approve(payload=self.payload())
        self.assertEqual(changed.status_code, 429)
        self.assertEqual(OfficialResearchRequest.objects.count(), 1)

    def test_cancel_is_authorized_csrf_post_only_and_idempotent(self):
        self.approve()
        obj = self.only()
        self.assertEqual(self.client.get(self.cancel_url()).status_code, 405)
        first = self.client.post(self.cancel_url())
        self.assertEqual(first.status_code, 302)
        obj.refresh_from_db()
        self.assertEqual(obj.status, "cancelled")
        self.assertIsNotNone(obj.cancelled_at)
        again = self.client.post(self.cancel_url())
        self.assertEqual(again.status_code, 302)
        self.assertEqual(OfficialResearchRequest.objects.count(), 1)
        self.assertContains(self.client.get(self.list_url), "Abgebrochen")
        attempted_retry = self.approve(payload={
            "expected_version": "1", "request_key": str(obj.request_key),
            "domain_rechecked": "on", "terms_rechecked": "on",
            "one_time_approved": "on",
        })
        self.assertEqual(attempted_retry.status_code, 409)
        self.assertEqual(OfficialResearchRequest.objects.count(), 1)

    def test_expired_status_visible_without_worker_and_explicit_cancel_marks_expired(self):
        self.approve()
        item = self.only()
        old = timezone.now() - timedelta(minutes=25)
        OfficialResearchRequest.objects.filter(pk=item.pk).update(
            consented_at=old,
            expires_at=old + timedelta(minutes=15),
        )
        item.refresh_from_db()
        self.assertEqual(item.status, "pending_worker")
        self.assertEqual(item.visible_status, "expired")
        r = self.client.get(self.list_url)
        self.assertContains(r, "Abgelaufen · nicht ausgeführt")
        self.assertNotContains(r, "Diese noch nicht ausgeführte Freigabe abbrechen")
        self.assertEqual(self.client.post(self.cancel_url()).status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, "expired")
        self.assertIsNone(item.cancelled_at)

    def test_new_source_on_same_job_after_cancel_still_honors_owner_daily_limit(self):
        self.approve()
        self.client.post(self.cancel_url())
        new_source = self.another_source()
        url = reverse(
            "research-approve-source",
            kwargs={"job_id": self.job.pk, "source_id": new_source.pk},
        )
        response = self.approve(payload=self.payload(url=url), url=url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OfficialResearchRequest.objects.count(), 2)
        self.assertEqual(OfficialResearchRequest.objects.filter(
            job=self.job, status="pending_worker",
        ).count(), 1)

    def test_per_user_domain_limit_applies_across_jobs_after_cancellation(self):
        self.approve()
        self.client.post(self.cancel_url())
        second_source = self.another_source(
            job=self.other_job, domain="club.example.org", context="club",
        )
        url = reverse(
            "research-approve-source",
            kwargs={"job_id": self.other_job.pk, "source_id": second_source.pk},
        )
        # Other owner has an independent quota, not a global domain ban.
        self.client.force_login(self.other)
        self.assertEqual(self.approve(payload=self.payload(url=url), url=url).status_code,
                         302)
        self.assertEqual(OfficialResearchRequest.objects.count(), 2)
        # A new job for the first owner on the same confirmed host is limited.
        new_job = ProductionJob.objects.create(
            owner=self.owner, club=self.job.club, title="Second story",
            country_code="AT", league_name="Austrian Bundesliga",
            club_name="Sturm Graz",
        )
        src = self.another_source(job=new_job, domain="club.example.org",
                                  context="club")
        again = reverse(
            "research-approve-source",
            kwargs={"job_id": new_job.pk, "source_id": src.pk},
        )
        self.client.force_login(self.owner)
        self.assertEqual(self.approve(payload=self.payload(url=again), url=again).status_code,
                         429)
        self.assertEqual(OfficialResearchRequest.objects.count(), 2)

    def test_daily_total_quota_applies_to_distinct_domains_and_jobs(self):
        for domain in ("league.example.org", "second.example.org"):
            job = ProductionJob.objects.create(
                owner=self.owner, club=self.job.club, title=f"Story {domain}",
                country_code="AT", league_name="Austrian Bundesliga",
                club_name="Sturm Graz",
            )
            source = self.another_source(job=job, domain=domain)
            url = reverse(
                "research-approve-source",
                kwargs={"job_id": job.pk, "source_id": source.pk},
            )
            self.assertEqual(
                self.approve(payload=self.payload(url=url), url=url).status_code, 302,
            )
        # Only two other jobs were consented above; a third is still fine.
        self.assertEqual(OfficialResearchRequest.objects.count(), 2)
        self.approve()  # Third consent.
        job = ProductionJob.objects.create(
            owner=self.owner, club=self.job.club, title="Fourth story",
            country_code="AT", league_name="Austrian Bundesliga",
            club_name="Sturm Graz",
        )
        src = self.another_source(job=job, domain="fourth.example.org")
        url = reverse(
            "research-approve-source",
            kwargs={"job_id": job.pk, "source_id": src.pk},
        )
        response = self.approve(payload=self.payload(url=url), url=url)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(OfficialResearchRequest.objects.count(), 3)

    def test_validation_missing_approval_and_forged_payload_cannot_create_request(self):
        valid = self.payload()
        for field in (
            "domain_rechecked", "terms_rechecked", "one_time_approved",
        ):
            with self.subTest(field=field):
                data = dict(valid)
                data[field] = ""
                response = self.approve(payload=data)
                self.assertEqual(response.status_code, 400)
        for change in (
            {"request_key": ""},
            {"request_key": "not-a-uuid"},
            {"request_key": str(UUID(int=1))},
            {"expected_version": "0"},
            {"expected_version": "abc"},
            {"expected_version": "9999999999"},
        ):
            with self.subTest(change=change):
                r = self.approve(payload={**valid, **change})
                self.assertEqual(r.status_code, 400)
        self.assertFalse(OfficialResearchRequest.objects.exists())
        attack = self.approve(payload={
            **valid, "url": "https://attacker.example.org/fetch",
            "domain": "attacker.example.org", "context": "league",
            "max_pages": "999999", "run_now": "on",
        })
        self.assertEqual(attack.status_code, 302)
        row = self.only()
        self.assertEqual(row.confirmed_url, self.source.url)
        self.assertEqual(row.confirmed_domain, "club.example.org")
        self.assertEqual((row.context, row.max_pages, row.attempt_count), ("club", 4, 0))
        self.assertNotContains(self.client.get(self.list_url), "attacker.example.org")

    def test_foreign_user_source_and_history_are_inaccessible(self):
        foreign_dossier = register_manual_official_source(
            owner=self.other, job_id=self.other_job.pk, expected_version=0,
            context="club", url="https://other.example.org/history",
            title="Other person's history", basis=BASIS,
            identity_confirmed=True, terms_confirmed=True, access_confirmed=True,
        )
        foreign = foreign_dossier.sources.get()
        forgery = reverse(
            "research-approve-source",
            kwargs={"job_id": self.job.pk, "source_id": foreign.pk},
        )
        self.assertEqual(self.client.get(forgery).status_code, 404)
        self.assertEqual(self.client.post(forgery, self.payload()).status_code, 404)
        self.client.logout()
        for url in (self.url, self.list_url):
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertEqual(self.client.post(url, {}).status_code, 302)
        self.client.force_login(self.other)
        for url in (self.url, self.list_url):
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {}).status_code, 404)
        self.client.force_login(self.owner)
        fork_dossier(job=self.job, previous=self.dossier)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.payload(
            url=reverse(
                "research-approve-source", kwargs={
                    "job_id": self.job.pk, "source_id": self.dossier.sources.get().pk,
                },
            )
        )).status_code, 404)

    def test_stale_version_blocks_service_even_with_current_source_id(self):
        next_dossier = fork_dossier(job=self.job, previous=self.dossier)
        current_source = next_dossier.sources.get(url=self.source.url)
        with self.assertRaises(ResearchConsentStale):
            record_one_time_research_consent(
                owner=self.owner, job_id=self.job.pk, source_id=current_source.pk,
                expected_version=1, request_key=uuid4(),
                domain_rechecked=True, terms_rechecked=True,
                one_time_approved=True,
            )
        self.assertFalse(OfficialResearchRequest.objects.exists())

    def test_imported_wikidata_and_corrupted_source_confirmation_are_forbidden(self):
        wiki = SourceReference.objects.create(
            dossier=self.dossier, source_kind="wikidata",
            url="https://club.example.org/wiki", title="Unapproved P856",
            retrieved_at=timezone.now(), access_state="accessible",
        )
        unconfirmed = SourceReference.objects.create(
            dossier=self.dossier, source_kind="club_official",
            url="https://club.example.org/other", title="Unconfirmed",
            retrieved_at=timezone.now(), access_state="accessible",
        )
        for src in (wiki, unconfirmed):
            with self.subTest(source=src.pk):
                url = reverse(
                    "research-approve-source",
                    kwargs={"job_id": self.job.pk, "source_id": src.pk},
                )
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(
                    url, self.payload(),
                ).status_code, 404)
        record = self.source.manual_confirmation
        for update in (
            {"confirmed_domain": "attacker.example.org"},
            {"identity_confirmed": False},
            {"terms_confirmed": False},
            {"access_confirmed": False},
            {"reviewer": self.other},
        ):
            with self.subTest(update=update):
                SourceConfirmation.objects.filter(pk=record.pk).update(**update)
                self.assertEqual(self.client.get(self.url).status_code, 404)
                self.assertEqual(self.client.post(
                    self.url, self.payload(
                        url=reverse("research-approve-source", kwargs={
                            "job_id": self.job.pk, "source_id": self.source.pk,
                        }),
                    ),
                ).status_code, 404)
                SourceConfirmation.objects.filter(pk=record.pk).update(
                    confirmed_domain="club.example.org",
                    identity_confirmed=True, terms_confirmed=True,
                    access_confirmed=True, reviewer=self.owner,
                )
        self.assertFalse(OfficialResearchRequest.objects.exists())

    def test_model_and_db_reject_invalid_references_and_excess_attempts(self):
        response = self.approve()
        self.assertEqual(response.status_code, 302)
        row = self.only()
        row.attempt_count = 2
        with self.assertRaises(ValidationError):
            row.save()
        row.refresh_from_db()
        self.assertEqual(row.attempt_count, 0)
        with self.assertRaises(IntegrityError):
            with self.captureOnCommitCallbacks(execute=True):
                OfficialResearchRequest.objects.filter(pk=row.pk).update(
                    attempt_count=2,
                )

    def test_xss_in_current_source_title_is_escaped(self):
        SourceReference.objects.filter(pk=self.source.pk).update(
            title="<script>alert(1)</script>",
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"<script>alert(1)</script>", response.content)

    @patch("socket.getaddrinfo")
    @patch("urllib.request.urlopen")
    @patch("app.production.safe_official_fetch._download_public_https")
    @patch("app.production.official_site_research.research_official_website")
    @patch("app.production.official_site_import.import_official_site_sources")
    def test_all_request_actions_never_fetch_or_create_facts(
        self, importer, researcher, downloader, http, dns,
    ):
        before = (FactDossier.objects.count(), SourceReference.objects.count(),
                  Fact.objects.count())
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.owner)
        get = csrf.get(self.url)
        self.assertEqual(get.status_code, 200)
        data = {
            "expected_version": "1",
            "request_key": str(get.context["form"].initial["request_key"]),
            "domain_rechecked": "on", "terms_rechecked": "on",
            "one_time_approved": "on",
        }
        self.assertEqual(csrf.post(self.url, data).status_code, 403)
        token = csrf.cookies["csrftoken"].value
        saved = csrf.post(self.url, data, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(csrf.get(saved.url).status_code, 200)
        cancel = self.cancel_url()
        self.assertEqual(csrf.post(cancel).status_code, 403)
        self.assertEqual(
            csrf.post(cancel, HTTP_X_CSRFTOKEN=token).status_code, 302,
        )
        self.assertEqual(before, (
            FactDossier.objects.count(), SourceReference.objects.count(),
            Fact.objects.count(),
        ))
        self.assertEqual(OfficialResearchRequest.objects.count(), 1)
        self.assertEqual(
            self.client.get(self.url).status_code, 200,
        )
        self.assertEqual(self.client.get(self.cancel_url()).status_code, 405)
        for mock in (importer, researcher, downloader, http, dns):
            mock.assert_not_called()
