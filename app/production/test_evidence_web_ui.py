"""Offline, owner/CSRF/version/rate regression for browser evidence reviews."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from app.clubs.models import Club, Country, League
from .dossier_versions import fork_dossier
from .manual_source_import import register_manual_official_source
from .models import (
    Evidence, Fact, FactDossier, FactReview, ProductionJob,
    SourceReference,
)


class EvidenceReviewWebTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="evidence-web-owner@example.org",
            password="evidence-Owner-Only-Test-2026",
        )
        self.other = User.objects.create_user(
            email="evidence-web-other@example.org",
            password="evidence-Other-Only-Test-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(
            country=country, name="Austrian Bundesliga",
        )
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club,
            title="The History of Sturm Graz", country_code="AT",
            league_name="Austrian Bundesliga", club_name="Sturm Graz",
        )
        self.other_job = ProductionJob.objects.create(
            owner=self.other, club=club,
            title="Other person's story", country_code="AT",
            league_name="Austrian Bundesliga", club_name="Sturm Graz",
        )
        self.original = register_manual_official_source(
            owner=self.owner, job_id=self.job.pk, expected_version=0,
            url="https://club.example.org/history",
            title="Official club history", context="club",
            basis=(
                "I personally checked the club identity and navigation "
                "to the history page."
            ),
            identity_confirmed=True, terms_confirmed=True,
            access_confirmed=True,
        )
        self.club_source = self.original.sources.get()
        self.wikidata = SourceReference.objects.create(
            dossier=self.original, url="https://www.wikidata.org/wiki/Q123",
            source_kind="wikidata", title="Wikidata candidate",
            retrieved_at=timezone.now(), access_state="accessible",
        )
        self.restricted = SourceReference.objects.create(
            dossier=self.original, url="https://club.example.org/private",
            source_kind="club_official", title="Access restricted",
            retrieved_at=timezone.now(), access_state="restricted",
        )
        self.unsafe = SourceReference.objects.create(
            dossier=self.original, url="javascript:alert(1)",
            source_kind="other", title="Not a public HTTPS source",
            retrieved_at=timezone.now(), access_state="accessible",
        )
        self.fact = Fact.objects.create(
            dossier=self.original, predicate="founded_year", value=1909,
            assertion_text="The club was founded in 1909.",
        )
        self.season_fact = Fact.objects.create(
            dossier=self.original, predicate="league_membership",
            value={"league": "Austrian Bundesliga", "season": "2025/26"},
            assertion_text=(
                "The club competed in the Austrian Bundesliga in 2025/26."
            ),
        )
        Evidence.objects.create(
            fact=self.fact, source=self.club_source,
            locator="History > Foundation",
            summary="Awaiting human comparison of the club history page.",
            role="unknown",
        )
        self.url = reverse(
            "research-review-evidence",
            kwargs={"job_id": self.job.pk, "fact_id": self.fact.pk},
        )
        self.viewer = reverse("research-job", kwargs={"job_id": self.job.pk})
        self.client.force_login(self.owner)

    def payload(self, **changes):
        values = {
            "expected_version": "1",
            "source": str(self.club_source.pk),
            "role": "supports",
            "locator": "History > Foundation 1909",
            "summary": (
                "The official club timeline describes the year 1909 "
                "as the founding year."
            ),
            "source_checked": "on",
        }
        values.update(changes)
        return values

    def latest(self):
        return FactDossier.objects.filter(job=self.job).order_by("-version").first()

    def test_get_displays_claim_sources_roles_attestation_and_prior_evidence(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sturm Graz")
        self.assertContains(response, "The club was founded in 1909.")
        self.assertContains(response, "Official club history")
        self.assertContains(response, "Manuell geprüft, kein Serverabruf")
        self.assertContains(response, "Wikidata candidate")
        self.assertContains(response, "History &gt; Foundation")
        self.assertContains(response, "Stützender Beleg")
        self.assertContains(response, "Widersprechender Beleg")
        self.assertContains(response, "Nur Hintergrund / Kontext")
        self.assertContains(response, "source_checked")
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'name="expected_version"')
        self.assertContains(response, 'value="1"')
        self.assertNotContains(response, "Access restricted")
        self.assertNotContains(response, "Not a public HTTPS source")
        self.assertNotIn(b'href="javascript:', response.content)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertFalse(FactReview.objects.exists())
        self.assertEqual(FactDossier.objects.count(), 1)

    def test_season_is_visible_on_seasonal_fact(self):
        url = reverse(
            "research-review-evidence",
            kwargs={"job_id": self.job.pk, "fact_id": self.season_fact.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Saison:")
        self.assertContains(response, "2025/26")

    def test_supporting_evidence_creates_complete_new_unverified_dossier(self):
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{self.viewer}?version=2#facts-heading")
        new = self.latest()
        self.assertEqual(new.version, 2)
        self.assertEqual(self.original.facts.count(), 2)
        self.assertEqual(self.original.sources.count(), 4)
        self.assertEqual(self.original.facts.get(pk=self.fact.pk).evidence.count(), 1)
        self.assertEqual(new.sources.count(), 4)
        self.assertEqual(new.facts.count(), 2)
        checked = new.facts.get(predicate="founded_year")
        self.assertEqual(checked.verification_state, "unverified")
        self.assertEqual(checked.evidence.count(), 2)
        support = checked.evidence.get(role="supports")
        self.assertEqual(support.source.dossier_id, new.pk)
        self.assertEqual(support.summary, self.payload()["summary"])
        self.assertFalse(FactReview.objects.exists())
        self.assertEqual(
            new.sources.get(url=self.club_source.url).manual_confirmation.basis,
            self.club_source.manual_confirmation.basis,
        )
        overview = self.client.get(response.url)
        self.assertContains(overview, "Stützender Beleg")
        self.assertContains(overview, "Ungeprüft")

    def test_contradiction_and_context_are_not_auto_verified(self):
        first = self.client.post(self.url, self.payload(role="contradicts"))
        self.assertEqual(first.status_code, 302)
        current = self.latest()
        second_fact = current.facts.get(predicate="founded_year")
        second_source = current.sources.get(url=self.club_source.url)
        other_url = reverse(
            "research-review-evidence",
            kwargs={"job_id": self.job.pk, "fact_id": second_fact.pk},
        )
        second = self.client.post(other_url, self.payload(
            expected_version=str(current.version), source=str(second_source.pk),
            role="context_only", locator="History > Background",
            summary="The page also explains historical background in a separate section.",
        ))
        self.assertEqual(second.status_code, 302)
        after = self.latest()
        self.assertEqual(after.version, 3)
        fact = after.facts.get(predicate="founded_year")
        self.assertEqual(fact.verification_state, "unverified")
        self.assertSetEqual(
            set(fact.evidence.values_list("role", flat=True)),
            {"unknown", "contradicts", "context_only"},
        )
        self.assertFalse(FactReview.objects.exists())
        html = self.client.get(self.viewer)
        self.assertContains(html, "Gegenbeleg / Widerspruch")

    def test_identical_post_again_is_idempotent_across_versions(self):
        first = self.client.post(self.url, self.payload())
        again = self.client.post(self.url, self.payload())
        self.assertEqual((first.status_code, again.status_code), (302, 302))
        self.assertEqual(first.url, again.url)
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 2)
        self.assertEqual(Evidence.objects.filter(role="supports").count(), 1)

    def test_changed_old_submission_is_stale_not_overwritten(self):
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 302)
        altered = self.client.post(self.url, self.payload(
            role="contradicts",
            summary="The historic page gives a conflicting alternative date of 1910.",
        ))
        self.assertEqual(altered.status_code, 409)
        self.assertContains(altered, "inzwischen geändert", status_code=409)
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 2)
        self.assertEqual(Evidence.objects.filter(role="contradicts").count(), 0)

    def test_review_on_stale_fact_or_wrong_source_is_blocked(self):
        owner2 = FactDossier.objects.create(job=self.other_job, version=1)
        foreign = SourceReference.objects.create(
            dossier=owner2, url="https://other.example.org/about",
            source_kind="club_official", title="Other person's source",
            retrieved_at=timezone.now(), access_state="accessible",
        )
        for src in (
            foreign.pk, self.restricted.pk, self.unsafe.pk, 99999999, "nope",
        ):
            with self.subTest(src=src):
                response = self.client.post(
                    self.url, self.payload(source=str(src)),
                )
                self.assertEqual(response.status_code, 400)
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 1)
        current = fork_dossier(job=self.job, previous=self.original)
        updated_fact = current.facts.get(predicate="founded_year")
        new_url = reverse(
            "research-review-evidence",
            kwargs={"job_id": self.job.pk, "fact_id": updated_fact.pk},
        )
        self.assertEqual(self.client.get(self.url).status_code, 404)
        changed_source = current.sources.get(url=self.club_source.url)
        self.assertEqual(self.client.post(
            new_url, self.payload(
                expected_version="2", source=str(self.club_source.pk),
            ),
        ).status_code, 400)
        self.assertEqual(self.client.post(
            self.url, self.payload(),
        ).status_code, 409)
        self.assertEqual(self.client.post(
            new_url, self.payload(
                expected_version="2", source=str(changed_source.pk),
                role="supports",
            ),
        ).status_code, 302)

    def test_foreign_user_and_wrong_fact_path_cannot_get_or_post(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 404)
        self.client.force_login(self.owner)
        other_fact = Fact.objects.create(
            dossier=FactDossier.objects.create(
                job=self.other_job, version=1,
            ),
            predicate="stadium_name", value="Other Ground",
            assertion_text="Other person's club stadium is Other Ground.",
        )
        foreign_url = reverse(
            "research-review-evidence",
            kwargs={"job_id": self.job.pk, "fact_id": other_fact.pk},
        )
        self.assertEqual(self.client.get(foreign_url).status_code, 404)
        self.assertEqual(self.client.post(
            foreign_url, self.payload(),
        ).status_code, 404)
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 1)

    def test_model_review_is_revoked_in_new_version_when_new_evidence_added(self):
        old_support = Evidence.objects.create(
            fact=self.fact, source=self.club_source, role="supports",
            locator="History > Foundation 1909",
            summary="A reviewer found the founding year in the original history section.",
        )
        self.fact.verification_state = "verified"
        self.fact.save(update_fields=["verification_state"])
        FactReview.objects.create(
            fact=self.fact, reviewer=self.owner, decision="verified",
            note="The official founding claim was manually checked against its original section.",
            checked_source=True,
        )
        old_review = self.fact.review
        response = self.client.post(
            self.url, self.payload(
                role="contradicts",
                locator="Alternative chronology > Foundation",
                summary="A different historical account offers a conflicting foundation year.",
            ),
        )
        self.assertEqual(response.status_code, 302)
        new = self.latest()
        new_fact = new.facts.get(predicate="founded_year")
        self.assertEqual(new_fact.verification_state, "unverified")
        self.assertFalse(FactReview.objects.filter(fact=new_fact).exists())
        self.assertEqual(self.fact.verification_state, "verified")
        self.assertEqual(self.fact.review.pk, old_review.pk)
        self.assertEqual(old_support.fact.dossier_id, self.original.pk)
        self.assertEqual(new_fact.evidence.filter(role="contradicts").count(), 1)

    def test_strict_fields_and_explicit_checked_consent(self):
        failures = [
            {"expected_version": "0"},
            {"expected_version": "abc"},
            {"expected_version": "9999999999"},
            {"role": "verified"},
            {"role": "unknown"},
            {"role": "rejected"},
            {"locator": ""},
            {"locator": "a"},
            {"locator": "A" * 181},
            {"summary": "too short"},
            {"summary": "A" * 351},
            {"source_checked": ""},
            {"summary": "<script>alert(1)</script> extra words to pass minimum"},
        ]
        for data in failures:
            with self.subTest(data=data):
                result = self.client.post(self.url, self.payload(**data))
                self.assertEqual(result.status_code, 400)
                self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 1)
        # Unsafe text may be echoed only as escaped text in a 400 response.
        xss = self.client.post(self.url, self.payload(
            summary="<script>alert(1)</script> plus extra information",
        ))
        self.assertEqual(xss.status_code, 400)
        self.assertContains(xss, "&lt;script&gt;", status_code=400)
        self.assertNotIn(b"<script>alert(1)</script>", xss.content)

    def test_throttle_is_cross_worker_dossier_version_based(self):
        current = self.original
        for _ in range(9):
            current = fork_dossier(job=self.job, previous=current)
        self.assertEqual(current.version, 10)
        fact = current.facts.get(predicate="founded_year")
        source = current.sources.get(url=self.club_source.url)
        url = reverse(
            "research-review-evidence",
            kwargs={"job_id": self.job.pk, "fact_id": fact.pk},
        )
        response = self.client.post(
            url, self.payload(
                expected_version="10", source=str(source.pk),
            ),
        )
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Zu viele neue Recherchestände", status_code=429)
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 10)

    def test_only_current_version_has_link(self):
        first = self.client.get(self.viewer)
        self.assertContains(first, "Konkrete Fundstelle prüfen und Belegrolle ergänzen")
        self.client.post(self.url, self.payload())
        previous = self.client.get(self.viewer + "?version=1")
        self.assertNotContains(previous, "Konkrete Fundstelle prüfen und Belegrolle ergänzen")
        now = self.client.get(self.viewer + "?version=2")
        self.assertContains(now, "Konkrete Fundstelle prüfen und Belegrolle ergänzen")

    def test_http_csrf_and_no_network(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.get(self.url).status_code, 200)
        self.assertEqual(client.post(self.url, self.payload()).status_code, 403)
        csrf_token = client.cookies["csrftoken"].value
        with patch("socket.getaddrinfo") as dns, patch(
            "urllib.request.urlopen"
        ) as opener, patch(
            "app.production.safe_official_fetch._download_public_https",
        ) as downloader:
            response = client.post(
                self.url, self.payload(), HTTP_X_CSRFTOKEN=csrf_token,
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(client.get(response.url).status_code, 200)
            dns.assert_not_called()
            opener.assert_not_called()
            downloader.assert_not_called()
        self.assertEqual(self.client.put(
            self.url, "invalid", content_type="text/plain",
        ).status_code, 405)

    def test_initially_empty_job_has_no_review_page(self):
        another = ProductionJob.objects.create(
            owner=self.owner, club=self.job.club,
            title="No research yet", country_code="AT",
            league_name="Austrian Bundesliga", club_name="Sturm Graz",
        )
        url = reverse(
            "research-review-evidence",
            kwargs={"job_id": another.pk, "fact_id": self.fact.pk},
        )
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.payload()).status_code, 404)
