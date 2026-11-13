"""Owner-only official honours action: web proof and CSRF/versions."""
from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from app.clubs.models import Club, Country, League
from .models import (
    Fact, FactDossier, ProductionJob, SourceConfirmation, SourceReference,
)
from .test_official_honours import QID, CLUB, LEAGUE, gathered
from .wikimedia_auto import AutoResearchError


class OfficialHonoursWebTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="official-honours-web-owner@example.org",
            password="Test-local-only-123456",
        )
        self.other = User.objects.create_user(
            email="official-honours-web-other@example.org",
            password="Test-local-only-123456",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(
            country=country, name="Austrian Bundesliga",
        )
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, country_code="AT",
            league_name="Austrian Bundesliga",
            club_name="Sturm Graz", title="The Club's Story",
        )
        self.dossier = FactDossier.objects.create(
            job=self.job, version=6,
        )
        SourceReference.objects.create(
            dossier=self.dossier, source_kind="wikidata",
            url=(
                "https://www.wikidata.org/wiki/Special:EntityData/"
                + QID + ".json"
            ),
            title="[auto] SK Sturm Graz",
            external_id=QID,
            retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
            access_state="accessible",
        )
        for url, kind, host in (
            (CLUB, "club_official", "sksturm.at"),
            (LEAGUE, "league_official", "www.bundesliga.at"),
        ):
            source = SourceReference.objects.create(
                dossier=self.dossier, source_kind=kind,
                url=url, title="Official source",
                retrieved_at=datetime(2026, 11, 11, tzinfo=timezone.utc),
                access_state="accessible",
            )
            SourceConfirmation.objects.create(
                source=source, reviewer=self.owner,
                checked_at=datetime(2026, 11, 11, tzinfo=timezone.utc),
                confirmed_domain=host,
                identity_confirmed=True, terms_confirmed=True,
                access_confirmed=True,
                basis="This is the official website of the relevant organization.",
            )
        Fact.objects.create(
            dossier=self.dossier, predicate="founded_year", value=1909,
            assertion_text="The club was founded in 1909.",
        )
        self.url = reverse(
            "research-auto-official-honours",
            kwargs={"job_id": self.job.pk},
        )
        self.research = reverse(
            "research-job", kwargs={"job_id": self.job.pk},
        )
        self.client.force_login(self.owner)

    def test_browser_offers_one_click_honours_button_no_manual_names(self):
        result = self.client.get(self.research)
        self.assertEqual(result.status_code, 200)
        self.assertContains(
            result, "Meisterschaften und Pokalsiege automatisch recherchieren",
        )
        self.assertContains(result, self.url)
        self.assertContains(result, 'name="expected_version" value="6"')
        self.assertNotContains(result, 'name="club_name"')
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.official_honours._gather_honours")
    def test_import_shows_years_and_discrepancy_in_new_version(self, fetch):
        fetch.return_value = gathered()
        result = self.client.post(self.url, {
            "expected_version": "6",
        })
        self.assertEqual(result.status_code, 302)
        self.assertEqual(result["Location"], self.research + "?version=7")
        page = self.client.get(result["Location"])
        self.assertContains(page, "Automatische Vereinschronik")
        self.assertContains(page, "2023/24")
        self.assertContains(page, "im ausgelesenen Vereinsprofil nicht aufgeführt")
        self.assertContains(page, "Übereinstimmung zwischen offizieller Liga")
        self.assertContains(page, "Meisterschaft")
        self.assertContains(page, "Pokal")
        self.assertContains(page, "11")
        self.assertNotContains(
            page, "Meisterschaften und Pokalsiege automatisch recherchieren",
        )
        self.assertEqual(FactDossier.objects.count(), 2)
        self.assertEqual(
            Fact.objects.filter(
                predicate="club_honour_candidate",
                verification_state="verified",
            ).count(), 0,
        )
        fetch.assert_called_once()

    @patch("app.production.official_honours._gather_honours")
    def test_one_click_repeat_no_repeat_fetch(self, fetch):
        fetch.return_value = gathered()
        first = self.client.post(self.url, {"expected_version": "6"})
        second = self.client.post(self.url, {"expected_version": "6"})
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(FactDossier.objects.count(), 2)
        fetch.assert_called_once()

    @patch("app.production.official_honours._gather_honours")
    def test_get_read_only_and_owner_scoped(self, fetch):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.research).status_code, 404)
        self.assertEqual(
            self.client.post(self.url, {"expected_version": "6"}).status_code,
            404,
        )
        fetch.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    def test_anonymous_requires_login(self):
        self.client.logout()
        self.assertEqual(
            self.client.post(self.url, {"expected_version": "6"}).status_code,
            302,
        )

    @patch("app.production.official_honours._gather_honours")
    def test_stale_and_malformed_versions_make_no_network_request(self, fetch):
        for raw in ("", "-1", "06", "0", "abc", "6<script>", "9999999999"):
            with self.subTest(raw=raw):
                self.assertEqual(
                    self.client.post(self.url, {
                        "expected_version": raw,
                    }).status_code, 404,
                )
        self.assertEqual(
            self.client.post(self.url, {"expected_version": "5"}).status_code,
            409,
        )
        fetch.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.official_honours._gather_honours")
    def test_robots_or_network_refusal_never_creates_version(self, fetch):
        for error in (
            "league_site_robots_disallowed",
            "league_site_access_restricted",
            "league_site_robots_unusable",
        ):
            fetch.side_effect = AutoResearchError(error)
            result = self.client.post(
                self.url, {"expected_version": "6"},
            )
            self.assertEqual(result.status_code, 503)
            self.assertNotIn(b"Traceback", result.content)
            self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.official_honours._gather_honours")
    def test_csrf_protects_external_site_fetch(self, fetch):
        fetch.return_value = gathered()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(
            client.post(self.url, {"expected_version": "6"}).status_code,
            403,
        )
        fetch.assert_not_called()
        client.get(self.research)
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post(self.url, {
            "expected_version": "6",
            "csrfmiddlewaretoken": token,
        }).status_code, 302)
        fetch.assert_called_once()
