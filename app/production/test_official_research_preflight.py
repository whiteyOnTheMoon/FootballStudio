"""Owner, provenance, no-network and snapshot security tests for M2 preflight."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from app.clubs.models import Club, Country, League

from .dossier_versions import fork_dossier
from .manual_source_import import register_manual_official_source
from .models import (
    Fact, FactDossier, ProductionJob, SourceConfirmation, SourceReference,
)
from .official_site_preflight import plan_confirmed_official_source


BASIS = (
    "I inspected the original club navigation and checked that this "
    "official history page belongs to the selected football club."
)


class OfficialResearchPreflightTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="preflight-owner@example.org",
            password="Only-For-Tests-Preflight-Owner-2026",
        )
        self.other = User.objects.create_user(
            email="preflight-other@example.org",
            password="Only-For-Tests-Preflight-Other-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, title="History of Sturm Graz",
            country_code="AT", league_name="Austrian Bundesliga",
            club_name="Sturm Graz",
        )
        self.other_job = ProductionJob.objects.create(
            owner=self.other, club=club, title="Private history",
            country_code="AT", league_name="Austrian Bundesliga",
            club_name="Sturm Graz",
        )
        self.url = reverse("research-preflight", kwargs={"job_id": self.job.pk})
        self.viewer = reverse("research-job", kwargs={"job_id": self.job.pk})
        self.client.force_login(self.owner)

    def register(self, *, owner=None, job_id=None, context="club",
                 url="https://club.example.org/history", title="Official history",
                 basis=BASIS):
        job_id = self.job.pk if job_id is None else job_id
        last = FactDossier.objects.filter(job_id=job_id).order_by("-version").first()
        return register_manual_official_source(
            owner=owner or self.owner, job_id=job_id,
            expected_version=last.version if last else 0,
            context=context, url=url, title=title, basis=basis,
            identity_confirmed=True, terms_confirmed=True,
            access_confirmed=True,
        )

    def choose(self, source, **params):
        return self.client.get(self.url, {"source_id": str(source.pk), **params})

    def test_empty_job_get_shows_helpful_state_without_creating_dossier(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sturm Graz")
        self.assertContains(response, "noch kein Recherchedossier")
        self.assertContains(response, "Quelle zuerst selbst prüfen")
        self.assertContains(response, "kein Websiteabruf")
        self.assertContains(response, "keine Website")
        self.assertNotContains(response, "<form", html=False)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertFalse(FactDossier.objects.exists())
        self.assertContains(
            self.client.get(self.viewer),
            "Offizielle Quellen und Recherchegrenzen vorab prüfen",
        )

    def test_valid_confirmed_source_displays_owner_provenance_and_limits(self):
        dossier = self.register()
        source = dossier.sources.get()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vorabprüfung dieser Quelle ansehen")
        self.assertContains(response, "Official history")
        self.assertContains(response, "club.example.org")
        self.assertNotContains(response, "bis zu 3 relevante")
        selected = self.choose(source)
        self.assertEqual(selected.status_code, 200)
        self.assertContains(selected, "Ausgangsseite")
        self.assertContains(selected, source.url)
        self.assertContains(selected, "https://club.example.org/robots.txt")
        self.assertContains(selected, BASIS)
        self.assertContains(selected, "Verein Sturm Graz")
        self.assertContains(selected, "Vereinsgeschichte / Chronik")
        self.assertContains(selected, "Titel und Erfolge")
        self.assertContains(selected, "Stadion")
        self.assertContains(selected, "Höchstens 4 HTML-Seiten")
        self.assertContains(selected, "bis zu 3")
        self.assertContains(selected, "nicht startbar")
        self.assertContains(selected, "kein Websiteabruf")
        self.assertEqual(selected.context["selected"].max_total_pages, 4)
        self.assertEqual(selected.context["selected"].max_subpages, 3)
        self.assertEqual(selected.context["selected"].confirmation_reviewer_id,
                         self.owner.pk)
        self.assertEqual(FactDossier.objects.count(), 1)
        self.assertFalse(Fact.objects.exists())

    def test_league_planning_has_own_categories_and_club_context_isolated(self):
        self.register()
        second = self.register(
            context="league", url="https://league.example.org/table",
            title="Official league standings",
            basis=(
                "I checked this standings page directly from the league's "
                "official navigation and club competition listings."
            ),
        )
        league_source = second.sources.get(source_kind="league_official")
        club_source = second.sources.get(source_kind="club_official")
        league_response = self.choose(league_source)
        self.assertEqual(league_response.status_code, 200)
        self.assertContains(league_response, "Liga Austrian Bundesliga")
        self.assertContains(league_response, "Tabelle / Tabellenstände")
        self.assertContains(league_response, "Spielplan")
        self.assertContains(league_response, "Ergebnisse")
        self.assertContains(league_response, "https://league.example.org/robots.txt")
        self.assertNotContains(league_response, "Vereinsgeschichte / Chronik")
        club_response = self.choose(club_source)
        self.assertContains(club_response, "Verein Sturm Graz")
        self.assertContains(club_response, "Vereinsgeschichte / Chronik")
        self.assertEqual(second.sources.count(), 2)

    def test_historical_source_id_is_not_valid_after_dossier_fork(self):
        first = self.register()
        original = first.sources.get()
        self.assertEqual(self.choose(original).status_code, 200)
        second = fork_dossier(job=self.job, previous=first)
        current = second.sources.get(url=original.url)
        self.assertNotEqual(original.pk, current.pk)
        self.assertEqual(self.choose(original).status_code, 404)
        self.assertEqual(self.choose(current).status_code, 200)
        self.assertEqual(second.version, 2)
        old_page = self.client.get(self.viewer + "?version=1")
        self.assertNotContains(
            old_page, "Offizielle Quellen und Recherchegrenzen vorab prüfen",
        )
        self.assertContains(
            self.client.get(self.viewer + "?version=2"),
            "Offizielle Quellen und Recherchegrenzen vorab prüfen",
        )

    def test_unconfirmed_wikidata_and_imported_references_never_appear(self):
        first = FactDossier.objects.create(job=self.job, version=1)
        wiki = SourceReference.objects.create(
            dossier=first, source_kind="wikidata", title="P856 candidate",
            url="https://club.example.org/home",
            retrieved_at=timezone.now(), access_state="accessible",
        )
        imported = SourceReference.objects.create(
            dossier=first, source_kind="club_official", title="Imported",
            url="https://other.example.org/history",
            retrieved_at=timezone.now(), access_state="accessible",
        )
        view = self.client.get(self.url)
        self.assertEqual(view.status_code, 200)
        self.assertNotContains(view, "P856 candidate")
        self.assertNotContains(view, "Imported")
        self.assertNotContains(view, "Vorabprüfung dieser Quelle ansehen")
        self.assertEqual(self.choose(wiki).status_code, 404)
        self.assertEqual(self.choose(imported).status_code, 404)

    def test_wrong_owner_and_foreign_job_source_both_get_404(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.post(self.url, {}).status_code, 302)
        self.register()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(self.url + "?source_id=1").status_code, 404)
        foreign = self.register(
            owner=self.other, job_id=self.other_job.pk,
            url="https://other.example.org/team",
            title="Other club identity",
            basis="I independently inspected the official page for the unrelated job.",
        ).sources.get()
        self.client.force_login(self.owner)
        self.assertEqual(self.choose(foreign).status_code, 404)
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 1)

    def test_untrusted_malformed_or_out_of_range_source_selector_returns_404(self):
        first = self.register()
        for value in (
            "", "0", "-1", "01", "abc", "1%2f2", "999999999999999999999",
            "9" * 5000, "<script>alert(1)</script>",
        ):
            with self.subTest(source_id=value):
                response = self.client.get(self.url, {"source_id": value})
                self.assertEqual(response.status_code, 404)
        self.assertEqual(self.choose(first.sources.get()).status_code, 200)

    def test_corrupted_confirmation_or_source_ref_fails_closed(self):
        dossier = self.register()
        source = dossier.sources.get()
        saved = source.manual_confirmation
        cases = [
            ("confirmation", {"confirmed_domain": "evil.example.org"}),
            ("confirmation", {"identity_confirmed": False}),
            ("confirmation", {"terms_confirmed": False}),
            ("confirmation", {"access_confirmed": False}),
            ("confirmation", {"reviewer": self.other}),
            ("confirmation", {"basis": "x"}),
            ("source", {"access_state": "restricted"}),
            ("source", {"source_kind": "news"}),
            ("source", {"url": "http://club.example.org/history"}),
            ("source", {"url": "https://localhost/" }),
            ("source", {"url": "https://transfermarkt.de/news"}),
            ("source", {"url": "https://evil.example.org/history"}),
        ]
        for model, fields in cases:
            with self.subTest(model=model, fields=fields):
                if model == "confirmation":
                    SourceConfirmation.objects.filter(pk=saved.pk).update(**fields)
                else:
                    SourceReference.objects.filter(pk=source.pk).update(**fields)
                self.assertEqual(self.choose(source).status_code, 404)
                self.assertNotContains(
                    self.client.get(self.url),
                    "Vorabprüfung dieser Quelle ansehen",
                )
                SourceConfirmation.objects.filter(pk=saved.pk).update(
                    reviewer=self.owner,
                    confirmed_domain="club.example.org",
                    identity_confirmed=True, terms_confirmed=True,
                    access_confirmed=True, basis=BASIS,
                )
                SourceReference.objects.filter(pk=source.pk).update(
                    source_kind="club_official",
                    url="https://club.example.org/history",
                    access_state="accessible",
                )

    def test_future_confirmation_does_not_count_as_existing_verification(self):
        from datetime import timedelta
        source = self.register().sources.get()
        SourceConfirmation.objects.filter(source=source).update(
            checked_at=timezone.now() + timedelta(days=3),
        )
        self.assertEqual(self.choose(source).status_code, 404)

    def test_xss_in_saved_source_title_is_escaped_not_executed(self):
        source = self.register().sources.get()
        SourceReference.objects.filter(pk=source.pk).update(
            title="<script>alert(1)</script>",
        )
        response = self.choose(source)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script&gt;", html=False)
        self.assertNotIn(b"<script>alert(1)</script>", response.content)

    @patch("socket.getaddrinfo")
    @patch("urllib.request.urlopen")
    @patch("app.production.safe_official_fetch._download_public_https")
    @patch("app.production.official_site_research.research_official_website")
    @patch("app.production.official_site_import.import_official_site_sources")
    def test_all_gets_are_strictly_no_network_and_no_mutations(
        self, importer, researcher, download, http, dns,
    ):
        source = self.register().sources.get()
        count = (
            FactDossier.objects.count(),
            SourceReference.objects.count(),
            SourceConfirmation.objects.count(),
            Fact.objects.count(),
        )
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        self.assertEqual(browser.get(self.url).status_code, 200)
        self.assertEqual(
            browser.get(self.url, {"source_id": str(source.pk)}).status_code,
            200,
        )
        self.assertEqual(
            browser.post(
                self.url, {"source_id": str(source.pk), "allow_crawl": "on"},
            ).status_code, 405,
        )
        self.assertEqual(
            browser.put(self.url, "body", content_type="text/plain").status_code,
            405,
        )
        self.assertEqual(
            browser.delete(self.url).status_code, 405,
        )
        self.assertEqual(
            count,
            (
                FactDossier.objects.count(),
                SourceReference.objects.count(),
                SourceConfirmation.objects.count(),
                Fact.objects.count(),
            ),
        )
        for mock in (importer, researcher, download, http, dns):
            mock.assert_not_called()

    def test_query_parameters_never_become_a_new_url_or_automatic_fetch(self):
        source = self.register().sources.get()
        response = self.client.get(self.url, {
            "source_id": str(source.pk),
            "url": "https://attacker.example.org/secret",
            "context": "league",
            "fetch": "1",
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "attacker.example.org")
        self.assertContains(response, "Verein Sturm Graz")
        self.assertEqual(SourceReference.objects.count(), 1)
