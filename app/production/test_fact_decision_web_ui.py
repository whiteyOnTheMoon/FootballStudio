"""Offline regression for explicit owner-attributed fact decisions in HTML."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from app.clubs.models import Club, Country, League

from .dossier_versions import fork_dossier
from .manual_source_import import register_manual_official_source
from .models import Evidence, Fact, FactDossier, FactReview, ProductionJob, SourceReference


REVIEW_NOTE = (
    "I personally checked the original source section against the exact "
    "claim and found a clear, time-specific supporting statement."
)
CONFLICT_NOTE = (
    "I compared both source locations and found contradictory statements "
    "that cannot be reconciled without further independent research."
)


class FactDecisionBrowserTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="fact-decision-owner@example.org",
            password="Only-For-Tests-Fact-Decision-2026",
        )
        self.other = User.objects.create_user(
            email="fact-decision-other@example.org",
            password="Only-For-Tests-Other-Fact-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club,
            country_code="AT", league_name="Austrian Bundesliga",
            club_name="Sturm Graz", title="Sturm Graz researched history",
        )
        self.other_job = ProductionJob.objects.create(
            owner=self.other, club=club,
            country_code="AT", league_name="Austrian Bundesliga",
            club_name="Sturm Graz", title="Private unrelated story",
        )
        self.original = register_manual_official_source(
            owner=self.owner, job_id=self.job.pk, expected_version=0,
            context="club", url="https://club.example.org/history",
            title="Official club history",
            basis="I verified the official club navigation and its founding history section.",
            identity_confirmed=True, terms_confirmed=True,
            access_confirmed=True,
        )
        self.source = self.original.sources.get()
        self.fact = Fact.objects.create(
            dossier=self.original, predicate="founded_year", value=1909,
            assertion_text="The football club was founded in 1909.",
        )
        self.seasonal = Fact.objects.create(
            dossier=self.original, predicate="league_membership",
            value={"league": "Austrian Bundesliga", "season": "2025/26"},
            assertion_text="The club played in the Austrian Bundesliga in 2025/26.",
        )
        self.no_support = Fact.objects.create(
            dossier=self.original, predicate="stadium_name",
            value="Example Arena",
            assertion_text="The club plays at Example Arena.",
        )
        self.support = Evidence.objects.create(
            fact=self.fact, source=self.source, role="supports",
            locator="History > Foundation 1909",
            summary="The club timeline identifies 1909 as the year of foundation.",
        )
        self.fact_url = self.url_for(self.fact.pk)
        self.viewer = reverse("research-job", kwargs={"job_id": self.job.pk})
        self.client.force_login(self.owner)

    def url_for(self, fact_id):
        return reverse(
            "research-decide-fact",
            kwargs={"job_id": self.job.pk, "fact_id": fact_id},
        )

    def payload(self, **updates):
        data = {
            "expected_version": "1",
            "decision": "verified",
            "review_note": REVIEW_NOTE,
            "source_checked": "on",
            "review_confirmed": "on",
        }
        data.update(updates)
        return data

    def latest(self):
        return FactDossier.objects.filter(job=self.job).order_by("-version").first()

    def fact_in(self, dossier, predicate):
        return dossier.facts.get(predicate=predicate)

    def test_current_dossier_has_review_links_not_historical_dossier(self):
        current = self.client.get(self.viewer)
        self.assertContains(current, "Fakt bewusst prüfen und Entscheidung dokumentieren")
        self.assertContains(current, self.fact_url)
        self.assertNotContains(current, "/some/nonexistent/url")
        second = fork_dossier(job=self.job, previous=self.original)
        old_page = self.client.get(self.viewer + "?version=1")
        self.assertNotContains(
            old_page, "Fakt bewusst prüfen und Entscheidung dokumentieren",
        )
        new_page = self.client.get(self.viewer + "?version=2")
        self.assertContains(
            new_page, "Fakt bewusst prüfen und Entscheidung dokumentieren",
        )
        self.assertEqual(self.client.get(self.fact_url).status_code, 404)
        current_fact = self.fact_in(second, "founded_year")
        self.assertEqual(self.client.get(self.url_for(current_fact.pk)).status_code, 200)

    def test_get_shows_claim_evidence_source_audit_and_review_controls(self):
        response = self.client.get(self.fact_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sturm Graz")
        self.assertContains(response, self.fact.assertion_text)
        self.assertContains(response, "History &gt; Foundation 1909")
        self.assertContains(response, "Originalquelle selbst ansehen")
        self.assertContains(response, "Manuell geprüft, kein Serverabruf")
        self.assertContains(response, "Keine automatische Wahrheitsprüfung")
        self.assertContains(response, "Verifiziert")
        self.assertContains(response, "Widersprüchlich")
        self.assertContains(response, "Nicht ausreichend belegt")
        self.assertContains(response, "Verworfen")
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'name="expected_version"')
        self.assertContains(response, 'name="review_confirmed"')
        self.assertContains(response, 'name="source_checked"')
        self.assertNotContains(response, 'name="season_checked"')
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(FactReview.objects.count(), 0)
        self.assertEqual(FactDossier.objects.count(), 1)

    def test_verified_requires_explicit_review_and_keeps_older_fact_unverified(self):
        reply = self.client.post(self.fact_url, self.payload())
        self.assertEqual(reply.status_code, 302)
        self.assertEqual(reply.url, f"{self.viewer}?version=2#facts-heading")
        newer = self.latest()
        self.assertEqual(newer.version, 2)
        old = self.fact_in(self.original, "founded_year")
        current = self.fact_in(newer, "founded_year")
        self.assertEqual(old.verification_state, "unverified")
        self.assertEqual(current.verification_state, "verified")
        self.assertNotEqual(old.pk, current.pk)
        record = current.review
        self.assertEqual(record.reviewer_id, self.owner.pk)
        self.assertEqual(record.note, REVIEW_NOTE)
        self.assertTrue(record.checked_source)
        self.assertFalse(record.checked_season)
        self.assertLess((timezone.now() - record.reviewed_at).total_seconds(), 60)
        self.assertEqual(current.evidence.get(role="supports").source.dossier_id, newer.pk)
        self.assertFalse(FactReview.objects.filter(fact=old).exists())
        html = self.client.get(reply.url)
        self.assertContains(html, "Verifiziert")
        self.assertContains(html, REVIEW_NOTE)
        self.assertContains(html, "Prüfer-ID")
        self.assertEqual(FactDossier.objects.count(), 2)

    def test_identical_old_submission_and_same_current_review_are_idempotent(self):
        first = self.client.post(self.fact_url, self.payload())
        replay = self.client.post(self.fact_url, self.payload())
        self.assertEqual((first.status_code, replay.status_code), (302, 302))
        self.assertEqual(first.url, replay.url)
        latest = self.latest()
        current = self.fact_in(latest, "founded_year")
        same_current = self.client.post(
            self.url_for(current.pk),
            self.payload(expected_version="2"),
        )
        self.assertEqual(same_current.status_code, 302)
        self.assertEqual(same_current.url, first.url)
        self.assertEqual(FactDossier.objects.count(), 2)
        self.assertEqual(FactReview.objects.count(), 1)

    def test_changed_submission_from_old_version_is_conflict(self):
        self.client.post(self.fact_url, self.payload())
        response = self.client.post(self.fact_url, self.payload(
            decision="rejected",
            review_note="The claim is not sufficiently justified and must not appear in the script.",
            source_checked="",
        ))
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "inzwischen geändert", status_code=409)
        self.assertEqual(FactDossier.objects.count(), 2)
        self.assertEqual(FactReview.objects.count(), 1)

    def test_rejected_or_insufficient_are_explicit_but_not_verified(self):
        rejected = self.client.post(self.fact_url, self.payload(
            decision="rejected",
            source_checked="",
            review_note="The club claim is not reliable enough to use in a documentary script.",
        ))
        self.assertEqual(rejected.status_code, 302)
        after = self.latest()
        self.assertEqual(self.fact_in(after, "founded_year").verification_state, "rejected")
        self.assertFalse(self.fact_in(after, "founded_year").review.checked_source)

        fact = self.fact_in(after, "stadium_name")
        insufficient = self.client.post(
            self.url_for(fact.pk),
            self.payload(
                expected_version="2", decision="insufficient_sources",
                source_checked="",
                review_note="No source location currently supports this stadium claim well enough.",
            ),
        )
        self.assertEqual(insufficient.status_code, 302)
        latest = self.latest()
        self.assertEqual(latest.version, 3)
        self.assertEqual(
            self.fact_in(latest, "stadium_name").verification_state,
            "insufficient_sources",
        )
        self.assertEqual(
            self.fact_in(latest, "founded_year").review.reviewed_at,
            self.fact_in(after, "founded_year").review.reviewed_at,
        )
        self.assertEqual(
            self.fact_in(after, "stadium_name").verification_state, "unverified",
        )

    def test_verified_without_support_and_unchecked_sources_are_rejected(self):
        no_source_url = self.url_for(self.no_support.pk)
        response = self.client.post(no_source_url, self.payload())
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "stützende Fundstelle", status_code=400)
        unchecked = self.client.post(self.fact_url, self.payload(source_checked=""))
        self.assertEqual(unchecked.status_code, 400)
        self.assertContains(unchecked, "persönliche Prüfung", status_code=400)
        self.assertEqual(FactDossier.objects.count(), 1)
        self.assertFalse(FactReview.objects.exists())

    def test_conflict_needs_both_roles_and_blocks_verification(self):
        incomplete = self.client.post(self.fact_url, self.payload(
            decision="conflicted", review_note=CONFLICT_NOTE,
        ))
        self.assertEqual(incomplete.status_code, 400)
        self.assertContains(incomplete, "stützende und widersprechende", status_code=400)
        Evidence.objects.create(
            fact=self.fact, source=self.source, role="contradicts",
            locator="History > Alternative foundation date 1910",
            summary="Another timeline provides a conflicting foundation year of 1910.",
        )
        blocked = self.client.post(self.fact_url, self.payload())
        self.assertEqual(blocked.status_code, 400)
        self.assertContains(blocked, "Ungeklärte Gegenbelege", status_code=400)
        decided = self.client.post(self.fact_url, self.payload(
            decision="conflicted", review_note=CONFLICT_NOTE,
        ))
        self.assertEqual(decided.status_code, 302)
        current = self.fact_in(self.latest(), "founded_year")
        self.assertEqual(current.verification_state, "conflicted")
        self.assertEqual(current.review.decision, "conflicted")
        self.assertEqual(self.latest().version, 2)
        self.assertEqual(self.fact_in(self.original, "founded_year").verification_state,
                         "unverified")

    def test_season_review_requires_explicit_crosscheck_and_matching_support(self):
        url = self.url_for(self.seasonal.pk)
        Evidence.objects.create(
            fact=self.seasonal, source=self.source,
            role="supports", locator="Results > Previous season",
            summary="The source covers a different competition season.",
        )
        response = self.client.get(url)
        self.assertContains(response, "Bezugszeit / Saison:")
        self.assertContains(response, "2025/26")
        self.assertContains(response, 'name="season_checked"')
        not_checked = self.client.post(url, self.payload())
        self.assertEqual(not_checked.status_code, 400)
        self.assertContains(not_checked, "Saison geprüft", status_code=400)
        wrong_season = self.client.post(url, self.payload(season_checked="on"))
        self.assertEqual(wrong_season.status_code, 400)
        self.assertContains(wrong_season, "Saison", status_code=400)
        self.assertEqual(FactDossier.objects.count(), 1)

    def test_season_review_with_matching_support_is_verified_and_attributed(self):
        Evidence.objects.create(
            fact=self.seasonal, source=self.source,
            role="supports",
            locator="Austrian Bundesliga 2025/26 > Seasonal overview",
            summary="The official results describe the club as participating in 2025/26.",
        )
        reply = self.client.post(
            self.url_for(self.seasonal.pk),
            self.payload(season_checked="on"),
        )
        self.assertEqual(reply.status_code, 302)
        item = self.fact_in(self.latest(), "league_membership")
        self.assertEqual(item.verification_state, "verified")
        self.assertTrue(item.review.checked_source)
        self.assertTrue(item.review.checked_season)
        self.assertEqual(item.review.reviewer_id, self.owner.pk)

    def test_required_fields_and_xss_are_rejected_without_new_version(self):
        failures = [
            {"expected_version": "0"},
            {"expected_version": "abc"},
            {"expected_version": "9999999999"},
            {"decision": "unverified"},
            {"decision": "supports"},
            {"review_note": "tiny"},
            {"review_note": "A" * 501},
            {"review_note": "<script>alert(1)</script> plus a longer malicious note for review"},
            {"review_confirmed": ""},
            {"source_checked": ""},
        ]
        for changes in failures:
            with self.subTest(changes=changes):
                response = self.client.post(self.fact_url, self.payload(**changes))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(FactDossier.objects.count(), 1)
                self.assertFalse(FactReview.objects.exists())
        xss = self.client.post(
            self.fact_url,
            self.payload(
                review_note="<script>alert(1)</script> plus a longer malicious note for review",
            ),
        )
        self.assertContains(xss, "&lt;script&gt;", status_code=400)
        self.assertNotIn(b"<script>alert(1)</script>", xss.content)

    def test_login_owner_and_forged_fact_ids_are_rejected(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.fact_url).status_code, 302)
        self.assertEqual(self.client.post(self.fact_url, self.payload()).status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.fact_url).status_code, 404)
        self.assertEqual(self.client.post(self.fact_url, self.payload()).status_code, 404)
        foreign_dossier = FactDossier.objects.create(job=self.other_job, version=1)
        foreign_fact = Fact.objects.create(
            dossier=foreign_dossier, predicate="stadium_name",
            value="Private Arena",
            assertion_text="Other owner's private club stadium information.",
        )
        self.client.force_login(self.owner)
        forged = self.url_for(foreign_fact.pk)
        self.assertEqual(self.client.get(forged).status_code, 404)
        self.assertEqual(self.client.post(forged, self.payload()).status_code, 404)
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 1)

    def test_version_not_found_and_job_with_no_dossier_are_404(self):
        url = self.url_for(self.fact.pk)
        self.assertEqual(
            self.client.post(url, self.payload(expected_version="999")).status_code, 404,
        )
        job = ProductionJob.objects.create(
            owner=self.owner, club=self.job.club,
            title="Unresearched club", country_code="AT",
            league_name="Austrian Bundesliga", club_name="Sturm Graz",
        )
        missing = reverse(
            "research-decide-fact", kwargs={"job_id": job.pk, "fact_id": self.fact.pk},
        )
        self.assertEqual(self.client.get(missing).status_code, 404)
        self.assertEqual(self.client.post(missing, self.payload()).status_code, 404)

    def test_duplicate_only_with_immediate_unchanged_review_snapshot(self):
        first = self.client.post(self.fact_url, self.payload())
        self.assertEqual(first.status_code, 302)
        current = self.latest()
        next_dossier = fork_dossier(job=self.job, previous=current)
        repeated = self.client.post(self.fact_url, self.payload())
        self.assertEqual(repeated.status_code, 409)
        self.assertContains(repeated, "inzwischen geändert", status_code=409)
        self.assertEqual(self.latest().version, next_dossier.version)

    def test_per_job_db_rate_limit_blocks_mutations_but_allows_same_review(self):
        current = self.original
        for _ in range(9):
            current = fork_dossier(job=self.job, previous=current)
        old_fact = self.fact_in(current, "founded_year")
        url = self.url_for(old_fact.pk)
        blocked = self.client.post(url, self.payload(expected_version="10"))
        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, "Zu viele neue Recherchestände", status_code=429)
        self.assertFalse(FactReview.objects.exists())
        self.assertEqual(self.latest().version, 10)

    def test_csrf_method_protection_and_no_dns_http_or_apis(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.get(self.fact_url).status_code, 200)
        self.assertEqual(client.post(self.fact_url, self.payload()).status_code, 403)
        csrf = client.cookies["csrftoken"].value
        with patch("socket.getaddrinfo") as dns, patch(
            "urllib.request.urlopen"
        ) as http, patch(
            "app.production.safe_official_fetch._download_public_https"
        ) as downloader:
            accepted = client.post(
                self.fact_url, self.payload(), HTTP_X_CSRFTOKEN=csrf,
            )
            self.assertEqual(accepted.status_code, 302)
            self.assertEqual(client.get(accepted.url).status_code, 200)
            dns.assert_not_called()
            http.assert_not_called()
            downloader.assert_not_called()
        self.assertEqual(
            self.client.put(
                self.fact_url, "invalid", content_type="text/plain",
            ).status_code,
            405,
        )
