"""Database, owner, CSRF, no-network, provenance and dossier-version tests."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from app.clubs.models import Club, Country, League

from .dossiers import load_fact_dossier
from .dossier_versions import fork_dossier
from .manual_source_import import validate_manual_source_url
from .models import (
    Evidence, Fact, FactDossier, ProductionJob, SourceConfirmation,
    SourceReference,
)


BASIS = (
    "I checked the official club navigation and its own history page "
    "against the selected club identity."
)


class ManualSourceWebTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="manual-source-owner@example.org", password="Source-Test-Only-Owner-2026",
        )
        self.other = User.objects.create_user(
            email="manual-source-other@example.org", password="Source-Test-Only-Other-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, title="History of Sturm Graz",
            country_code="AT", league_name="Austrian Bundesliga", club_name="Sturm Graz",
        )
        self.url = reverse("research-new-source", kwargs={"job_id": self.job.pk})
        self.viewer = reverse("research-job", kwargs={"job_id": self.job.pk})
        self.fact_url = reverse("research-new-fact", kwargs={"job_id": self.job.pk})
        self.client.force_login(self.owner)

    def payload(self, **changes):
        values = {
            "expected_version": "0",
            "context": "club",
            "url": "https://club.example.org/history",
            "title": "Official club history",
            "basis": BASIS,
            "identity_confirmed": "on",
            "terms_confirmed": "on",
            "access_confirmed": "on",
        }
        values.update(changes)
        return values

    def register(self, **changes):
        return self.client.post(self.url, self.payload(**changes))

    def test_empty_job_links_to_owner_only_source_form(self):
        overview = self.client.get(self.viewer)
        self.assertEqual(overview.status_code, 200)
        self.assertContains(overview, "Für diesen Job liegt noch kein Faktendossier vor.")
        self.assertContains(overview, "Offizielle Quelle manuell bestätigen")
        form = self.client.get(self.url)
        self.assertEqual(form.status_code, 200)
        self.assertContains(form, "Sturm Graz")
        self.assertContains(form, "Austrian Bundesliga")
        self.assertContains(form, 'name="expected_version"')
        self.assertContains(form, 'value="0"')
        self.assertContains(form, 'name="csrfmiddlewaretoken"')
        self.assertContains(form, "identity_confirmed")
        self.assertContains(form, "terms_confirmed")
        self.assertContains(form, "access_confirmed")
        self.assertContains(form, "Keine automatische Recherche")
        self.assertIn("no-store", form["Cache-Control"])
        self.assertEqual(FactDossier.objects.count(), 0)

    def test_success_creates_manual_source_and_explicit_provenance_not_fact(self):
        response = self.register()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{self.viewer}?version=1#sources-heading")
        dossier = FactDossier.objects.get(job=self.job, version=1)
        source = dossier.sources.get()
        confirmation = source.manual_confirmation
        self.assertEqual(source.url, "https://club.example.org/history")
        self.assertEqual(source.source_kind, SourceReference.Kind.CLUB_OFFICIAL)
        self.assertEqual(source.access_state, SourceReference.Access.ACCESSIBLE)
        self.assertEqual(source.title, "Official club history")
        self.assertEqual(confirmation.reviewer_id, self.owner.pk)
        self.assertEqual(confirmation.confirmed_domain, "club.example.org")
        self.assertEqual(confirmation.basis, BASIS)
        self.assertTrue(confirmation.identity_confirmed)
        self.assertTrue(confirmation.terms_confirmed)
        self.assertTrue(confirmation.access_confirmed)
        self.assertEqual(source.retrieved_at, confirmation.checked_at)
        self.assertEqual(Fact.objects.count(), 0)
        self.assertEqual(Evidence.objects.count(), 0)
        snapshot = load_fact_dossier(owner=self.owner, job_id=self.job.pk, version=1)
        self.assertEqual(snapshot["sources"][0]["manual_confirmation"]["provenance"],
                         "user_entered_checked")
        self.assertEqual(snapshot["sources"][0]["manual_confirmation"]["reviewer_id"],
                         self.owner.pk)
        viewer = self.client.get(response.url)
        self.assertContains(viewer, "Manuell geprüft (kein Serverabruf)")
        self.assertContains(viewer, BASIS)
        self.assertContains(viewer, "Faktenvorschlag mit Quelle erfassen")
        self.assertContains(viewer, "keine Prüfung einzelner Aussagen")

    def test_manually_confirmed_source_supports_unverified_browser_fact_entry(self):
        self.register()
        dossier = FactDossier.objects.get(job=self.job, version=1)
        source = dossier.sources.get()
        fact_form = self.client.get(self.fact_url)
        self.assertEqual(fact_form.status_code, 200)
        self.assertContains(fact_form, "manuell geprüft")
        result = self.client.post(self.fact_url, {
            "expected_version": "1",
            "source": str(source.pk),
            "predicate": "founded_year",
            "founded_year": "1909",
            "assertion_text": "The club was founded in the year 1909.",
            "locator": "Official website > club history > foundation",
            "evidence_summary": "The official club page gives the year 1909 as its founding date.",
            "source_read_confirmed": "on",
        })
        self.assertEqual(result.status_code, 302)
        self.assertIn("?version=2", result.url)
        newest = FactDossier.objects.get(job=self.job, version=2)
        fact = newest.facts.get()
        self.assertEqual(fact.verification_state, "unverified")
        evidence = fact.evidence.get()
        self.assertEqual(evidence.role, "unknown")
        new_source = newest.sources.get()
        self.assertNotEqual(new_source.pk, source.pk)
        self.assertEqual(new_source.manual_confirmation.basis, BASIS)
        self.assertEqual(new_source.manual_confirmation.checked_at,
                         source.manual_confirmation.checked_at)
        self.assertEqual(new_source.manual_confirmation.reviewer_id, self.owner.pk)
        self.assertEqual(dossier.facts.count(), 0)

    def test_repeat_exact_submitted_form_is_idempotent(self):
        first = self.register()
        repeated = self.register()
        self.assertEqual((first.status_code, repeated.status_code), (302, 302))
        self.assertEqual(first.url, repeated.url)
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 1)
        self.assertEqual(SourceReference.objects.count(), 1)
        self.assertEqual(SourceConfirmation.objects.count(), 1)

    def test_league_source_added_to_new_version_without_changing_previous(self):
        self.register()
        club_first = FactDossier.objects.get(job=self.job, version=1)
        response = self.register(
            expected_version="1", context="league",
            url="https://league.example.org/standings",
            title="Official league table",
            basis="I verified the association of this table with the league's own navigation.",
        )
        self.assertEqual(response.status_code, 302)
        second = FactDossier.objects.get(job=self.job, version=2)
        self.assertEqual(club_first.sources.count(), 1)
        self.assertEqual(second.sources.count(), 2)
        self.assertEqual(second.sources.filter(source_kind="league_official").count(), 1)
        self.assertEqual(second.sources.filter(source_kind="club_official").count(), 1)
        self.assertEqual(SourceConfirmation.objects.filter(source__dossier=second).count(), 2)
        self.assertEqual(SourceConfirmation.objects.filter(source__dossier=club_first).count(), 1)
        league = second.sources.get(source_kind="league_official")
        self.assertEqual(league.manual_confirmation.confirmed_domain, "league.example.org")
        self.assertContains(self.client.get(self.viewer), "Offizielle Ligaseite")
        self.assertEqual(self.client.get(self.url).context["form"].initial["expected_version"], 2)

    def test_stale_unrelated_post_is_409_and_no_data_is_overwritten(self):
        self.register()
        retry_changed = self.register(
            url="https://second.example.org/history",
            title="Another official page",
        )
        self.assertEqual(retry_changed.status_code, 409)
        self.assertContains(retry_changed, "inzwischen geändert", status_code=409)
        self.assertEqual(FactDossier.objects.count(), 1)
        self.assertEqual(SourceReference.objects.count(), 1)

    def test_conflicting_metadata_or_existing_nonmanual_url_is_409(self):
        self.register()
        for change in (
            {"title": "Different source title"},
            {"context": "league"},
            {"basis": "I independently checked the domain in a different part of the page."},
        ):
            with self.subTest(change=change):
                response = self.register(**change)
                self.assertEqual(response.status_code, 409)
        self.assertEqual(FactDossier.objects.count(), 1)

        # A previously server-imported reference must not silently turn into
        # a manually confirmed source.
        latest = FactDossier.objects.get(job=self.job, version=1)
        second = fork_dossier(job=self.job, previous=latest)
        SourceReference.objects.create(
            dossier=second, url="https://league.example.org/table",
            source_kind=SourceReference.Kind.LEAGUE_OFFICIAL,
            title="Already imported", retrieved_at=latest.created_at,
            access_state=SourceReference.Access.ACCESSIBLE,
        )
        attempt = self.register(
            expected_version="2", url="https://league.example.org/table",
            context="league", title="Already imported",
        )
        self.assertEqual(attempt.status_code, 409)
        self.assertEqual(FactDossier.objects.count(), 2)

    def test_missing_flags_or_invalid_basis_title_context_is_400(self):
        for change in (
            {"identity_confirmed": ""},
            {"terms_confirmed": ""},
            {"access_confirmed": ""},
            {"context": "third_party"},
            {"title": "abc"},
            {"title": "<img src=x onerror=alert(1)>"},
            {"basis": "too short"},
            {"basis": "<script>alert(1)</script> other extra information"},
            {"expected_version": "abc"},
            {"expected_version": "-1"},
            {"expected_version": "9876543210"},
        ):
            with self.subTest(change=change):
                response = self.register(**change)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(FactDossier.objects.count(), 0)
                self.assertEqual(SourceReference.objects.count(), 0)

    def test_bad_urls_are_rejected_without_network(self):
        unsafe = (
            "http://club.example.org/history",
            "https://127.0.0.1/",
            "https://[::1]/",
            "https://localhost/",
            "https://server.local/",
            "https://server.internal/",
            "https://server.lan/",
            "https://server.home/",
            "https://server.example/",
            "https://server.invalid/",
            "https://server.test/",
            "https://server.onion/",
            "https://server.arpa/",
            "https://transfermarkt.de/club",
            "https://example.org:8443/history",
            "https://user:pass@example.org/history",
            "https://club.example.org/?page=1",
            "https://club.example.org/#history",
            "https://club.example.org/path%0d%0aevil",
            "https://club.example.org/path\\extra",
            "https://club.example.org/files/video.mp4",
            "https://club.example.org/path with spaces",
            "https://club.example.org/über-uns",
            "javascript:alert(1)",
            "https://10.0.0.1/",
        )
        for url in unsafe:
            with self.subTest(url=url):
                result = self.register(url=url)
                self.assertEqual(result.status_code, 400)
        self.assertFalse(SourceReference.objects.exists())
        self.assertFalse(FactDossier.objects.exists())
        self.assertEqual(validate_manual_source_url("https://club.example.org/")[0],
                         "https://club.example.org/")

    def test_xss_input_escaped_and_never_echoed_raw(self):
        response = self.register(title="<img src=x onerror=alert(1)>")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "&lt;img src=x onerror=alert(1)&gt;", html=False)
        self.assertNotIn(b"<img src=x", response.content)

    def test_ownership_and_authentication_checked_on_get_and_post(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 404)
        self.assertFalse(FactDossier.objects.exists())

    def test_csrf_requires_real_cookie_and_post_token(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        self.assertEqual(browser.get(self.url).status_code, 200)
        self.assertEqual(browser.post(self.url, self.payload()).status_code, 403)
        csrf = browser.cookies["csrftoken"].value
        success = browser.post(self.url, self.payload(), HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(success.status_code, 302)
        self.assertEqual(FactDossier.objects.count(), 1)

    def test_rate_limit_checks_db_versions_across_workers(self):
        from django.utils import timezone
        current = FactDossier.objects.create(job=self.job, version=1)
        for _ in range(9):
            current = fork_dossier(job=self.job, previous=current)
        self.assertEqual(current.version, 10)
        response = self.register(expected_version="10")
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Zu viele neue Recherchestände", status_code=429)
        self.assertEqual(FactDossier.objects.count(), 10)
        self.assertEqual(SourceConfirmation.objects.count(), 0)

    @patch("socket.getaddrinfo")
    @patch("urllib.request.urlopen")
    @patch("app.production.safe_official_fetch._download_public_https")
    def test_render_and_save_do_not_resolve_or_fetch_a_site(self, downloader, opener, dns):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.get(self.viewer).status_code, 200)
        self.assertEqual(self.register().status_code, 302)
        self.assertEqual(self.client.get(self.viewer).status_code, 200)
        dns.assert_not_called()
        downloader.assert_not_called()
        opener.assert_not_called()

    def test_source_confirmation_model_rejects_foreign_reviewer(self):
        self.register()
        dossier = FactDossier.objects.get(job=self.job, version=1)
        unconfirmed_source = SourceReference.objects.create(
            dossier=dossier, url="https://club.example.org/about",
            source_kind="club_official", title="Another page",
            retrieved_at=dossier.created_at, access_state="accessible",
        )
        with self.assertRaises(ValidationError):
            SourceConfirmation.objects.create(
                source=unconfirmed_source, reviewer=self.other,
                confirmed_domain="club.example.org",
                identity_confirmed=True, terms_confirmed=True,
                access_confirmed=True, basis=BASIS,
            )
        self.assertEqual(SourceConfirmation.objects.count(), 1)

    def test_no_confirmation_on_historical_imported_sources(self):
        first = FactDossier.objects.create(job=self.job, version=1)
        SourceReference.objects.create(
            dossier=first, url="https://www.wikidata.org/wiki/Q123",
            source_kind="wikidata", title="Wikidata",
            retrieved_at=first.created_at, access_state="accessible",
        )
        snapshot = load_fact_dossier(owner=self.owner, job_id=self.job.pk, version=1)
        self.assertIsNone(snapshot["sources"][0]["manual_confirmation"])
        res = self.client.get(self.viewer)
        self.assertNotContains(res, "Manuell geprüft (kein Serverabruf)")

    def test_source_form_rejects_non_get_post_methods(self):
        self.assertEqual(self.client.put(self.url, "abc", content_type="text/plain").status_code, 405)
        self.assertEqual(self.client.delete(self.url).status_code, 405)
