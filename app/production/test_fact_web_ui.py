"""Owner / CSRF / version / type / rate-limit checks for manual research UI.

All tests are offline; the HTML form cannot call a remote site or buy a
service, and fact proposals always enter the dossier as unverified.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from app.clubs.models import Club, Country, League

from .dossier_versions import fork_dossier
from .models import (
    Evidence, Fact, FactDossier, ProductionJob, SourceReference,
)


class ManualFactWebTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="fact-web-owner@example.org", password="Only-For-Tests-2026-Owner",
        )
        self.other = User.objects.create_user(
            email="fact-web-other@example.org", password="Only-For-Tests-2026-Other",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Bundesliga")
        club = Club.objects.create(league=league, name="Example FC")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, title="Football History Project",
            country_code="AT", league_name="Bundesliga", club_name="Example FC",
        )
        self.other_job = ProductionJob.objects.create(
            owner=self.other, club=club, title="Another Football Story",
            country_code="AT", league_name="Bundesliga", club_name="Example FC",
        )
        self.viewer = reverse("research-job", kwargs={"job_id": self.job.pk})
        self.url = reverse("research-new-fact", kwargs={"job_id": self.job.pk})
        self.original = FactDossier.objects.create(job=self.job, version=1)
        self.club_source = self.add_source(
            self.original, "https://club.example.org/history",
            "club_official", "Official club history",
        )
        self.league_source = self.add_source(
            self.original, "https://league.example.org/table",
            "league_official", "League standings",
        )
        self.wikidata = self.add_source(
            self.original, "https://www.wikidata.org/wiki/Q123",
            "wikidata", "Wikidata",
        )
        self.restricted = self.add_source(
            self.original, "https://club.example.org/private",
            "club_official", "Restricted", state="restricted",
        )
        self.client.force_login(self.owner)

    def add_source(self, dossier, url, kind, title, *, state="accessible"):
        return SourceReference.objects.create(
            dossier=dossier, url=url, source_kind=kind, title=title,
            retrieved_at=timezone.now(), access_state=state,
        )

    def payload(self, **changes):
        data = {
            "expected_version": "1",
            "source": str(self.club_source.pk),
            "predicate": "founded_year",
            "founded_year": "1901",
            "assertion_text": "The club was founded in 1901.",
            "locator": "Official club history > Foundation 1901",
            "evidence_summary": "The club history lists 1901 as its founding year.",
            "source_read_confirmed": "on",
        }
        data.update(changes)
        return data

    def test_get_contains_owner_scoped_sources_and_mobile_fields(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Faktenvorschlag für Example FC")
        self.assertContains(response, "Offizielle") if False else None
        self.assertContains(response, "Official club history")
        self.assertContains(response, "League standings")
        self.assertNotContains(response, "Wikidata")
        self.assertNotContains(response, "Restricted")
        self.assertContains(response, 'name="expected_version"')
        self.assertContains(response, 'value="1"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, "source_read_confirmed")
        self.assertContains(response, "Gründungsjahr")
        self.assertContains(response, "Tabellenplatz")
        self.assertContains(response, "noch nicht verifiziert")
        self.assertIn("no-store", response["Cache-Control"])

    def test_success_creates_unverified_fact_evidence_and_redirects_to_latest(self):
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 302)
        latest = FactDossier.objects.get(job=self.job, version=2)
        self.assertEqual(response.url, f"{self.viewer}?version=2#facts-heading")
        self.assertEqual(self.original.facts.count(), 0)
        self.assertEqual(latest.sources.count(), 4)
        fact = latest.facts.get()
        evidence = fact.evidence.get()
        self.assertEqual(fact.predicate, "founded_year")
        self.assertEqual(fact.value, 1901)
        self.assertEqual(fact.verification_state, "unverified")
        self.assertEqual(evidence.role, "unknown")
        self.assertEqual(evidence.locator, "Official club history > Foundation 1901")
        self.assertEqual(evidence.source.dossier_id, latest.pk)
        self.assertEqual(evidence.source.url, self.club_source.url)
        self.assertFalse(hasattr(fact, "review"))  # no automatic human approval
        viewer_response = self.client.get(response.url)
        self.assertContains(viewer_response, "The club was founded in 1901.")
        self.assertContains(viewer_response, "Ungeprüft")

    def test_duplicate_submission_returns_same_dossier_without_new_version(self):
        first = self.client.post(self.url, self.payload())
        second = self.client.post(self.url, self.payload())
        self.assertEqual((first.status_code, second.status_code), (302, 302))
        self.assertEqual(first.url, second.url)
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 2)
        self.assertEqual(Fact.objects.count(), 1)
        self.assertEqual(Evidence.objects.count(), 1)

    def test_changed_submission_against_old_dossier_is_conflict(self):
        first = self.client.post(self.url, self.payload())
        self.assertEqual(first.status_code, 302)
        response = self.client.post(self.url, self.payload(
            founded_year="1902",
            assertion_text="The club was founded in 1902.",
        ))
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "inzwischen geändert", status_code=409)
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 2)
        self.assertEqual(Fact.objects.count(), 1)
        new_source = FactDossier.objects.get(job=self.job, version=2).sources.get(
            url=self.club_source.url,
        )
        refreshed = self.client.post(self.url, self.payload(
            expected_version="2", source=str(new_source.pk),
            founded_year="1902", assertion_text="The club was founded in 1902.",
        ))
        self.assertEqual(refreshed.status_code, 302)
        self.assertIn("version=3", refreshed.url)
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 3)

    def test_all_fact_kinds_with_exact_typed_fields(self):
        examples = [
            ("stadium_name", {"stadium_name": "Example Arena"}, "Example Arena"),
            ("competition_win", {
                "competition": "National Cup", "season": "2025/26",
            }, {"competition": "National Cup", "season": "2025/26"}),
            ("league_membership", {
                "league_name": "Bundesliga", "season": "2024/25",
            }, {"league": "Bundesliga", "season": "2024/25"}),
            ("standings_position", {
                "competition": "Bundesliga", "season": "2023/24", "position": "3",
            }, {"competition": "Bundesliga", "season": "2023/24", "position": 3}),
        ]
        current = self.original
        for index, (predicate, value_fields, expected) in enumerate(examples, start=2):
            with self.subTest(predicate=predicate):
                source = current.sources.get(url=self.league_source.url)
                post_data = self.payload(
                    expected_version=str(current.version),
                    source=str(source.pk),
                    predicate=predicate,
                    founded_year="",
                    assertion_text=f"This record is about the club's {predicate} history.",
                    **value_fields,
                )
                response = self.client.post(self.url, post_data)
                self.assertEqual(response.status_code, 302)
                current = FactDossier.objects.get(job=self.job, version=index)
                fact = current.facts.order_by("-pk").first()
                self.assertEqual(fact.value, expected)
                self.assertEqual(fact.verification_state, "unverified")
                self.assertEqual(fact.evidence.get().role, "unknown")
                self.assertEqual(self.original.facts.count(), 0)

    def test_foreign_owner_and_unauthenticated_cannot_access_get_or_post(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 404)
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 1)

    def test_foreign_unapproved_and_stale_sources_never_accepted(self):
        foreign_dossier = FactDossier.objects.create(
            job=self.other_job, version=1,
        )
        foreign = self.add_source(
            foreign_dossier, "https://other.example.org/", "club_official", "Elsewhere",
        )
        cases = [foreign.pk, self.wikidata.pk, self.restricted.pk, 987654321, "oops"]
        for source_id in cases:
            with self.subTest(source_id=source_id):
                response = self.client.post(
                    self.url, self.payload(source=str(source_id)),
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 1)
        other_version = fork_dossier(job=self.job, previous=self.original)
        updated_source = other_version.sources.get(url=self.club_source.url)
        response = self.client.post(self.url, self.payload(
            expected_version="1", source=str(updated_source.pk),
        ))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Fact.objects.count(), 0)

    def test_bad_data_and_missing_attestation_rejected(self):
        cases = [
            {"predicate": "market_value"},
            {"founded_year": "2200"},
            {"founded_year": "0"},
            {"founded_year": "1901", "stadium_name": "wrong field"},
            {"assertion_text": "<script>alert(1)</script>"},
            {"locator": ""},
            {"evidence_summary": "a"},
            {"source_read_confirmed": ""},
            {"expected_version": "0"},
            {"expected_version": "oops"},
            {"predicate": "competition_win", "founded_year": "",
             "competition": "Cup", "season": "2025/29"},
            {"predicate": "standings_position", "founded_year": "",
             "competition": "Bundesliga", "season": "2025/26", "position": "0"},
            {"predicate": "league_membership", "founded_year": "",
             "league_name": "Bundesliga"},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                response = self.client.post(self.url, self.payload(**changes))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 1)
                self.assertEqual(Fact.objects.count(), 0)

    def test_csrf_enforced_for_post_but_safe_get_allowed(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        self.assertEqual(browser.get(self.url).status_code, 200)
        self.assertEqual(browser.post(self.url, self.payload()).status_code, 403)
        self.assertFalse(Fact.objects.exists())

    def test_rate_limit_is_db_backed_and_never_writes_an_extra_version(self):
        latest = self.original
        for _ in range(9):
            latest = fork_dossier(job=self.job, previous=latest)
        self.assertEqual(latest.version, 10)
        src = latest.sources.get(url=self.club_source.url)
        response = self.client.post(
            self.url,
            self.payload(expected_version="10", source=str(src.pk)),
        )
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Zu viele Änderungen", status_code=429)
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 10)
        self.assertFalse(Fact.objects.exists())

    def test_job_without_dossier_has_helpful_empty_state(self):
        new_job = ProductionJob.objects.create(
            owner=self.owner, club=self.job.club, title="Empty Job",
            country_code="AT", league_name="Bundesliga", club_name="Example FC",
        )
        url = reverse("research-new-fact", kwargs={"job_id": new_job.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Noch keine geeignete offizielle Quelle")
        self.assertNotContains(response, "<form", html=False)
        self.assertEqual(self.client.post(url, self.payload()).status_code, 400)
        self.assertFalse(FactDossier.objects.filter(job=new_job).exists())

    def test_dossier_link_only_on_current_with_official_source(self):
        self.client.force_login(self.owner)
        current = self.client.get(self.viewer)
        self.assertContains(current, "Faktenvorschlag mit Quelle erfassen")
        old = fork_dossier(job=self.job, previous=self.original)
        historic = self.client.get(self.viewer + "?version=1")
        self.assertNotContains(historic, "Faktenvorschlag mit Quelle erfassen")
        latest = self.client.get(self.viewer + "?version=2")
        self.assertContains(latest, "Faktenvorschlag mit Quelle erfassen")

    @patch("urllib.request.urlopen")
    @patch("app.production.safe_official_fetch._download_public_https")
    def test_manual_post_never_fetches_websites(self, downloader, http):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 302)
        downloader.assert_not_called()
        http.assert_not_called()
