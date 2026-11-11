"""Owner-scoped read-only research UI: security, history and XSS regression."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from app.clubs.models import Club, Country, League

from .dossier_versions import fork_dossier
from .models import (
    Evidence, Fact, FactDossier, FactReview, ProductionJob, SourceReference,
)


class ReadOnlyResearchPageTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="dossier-viewer@example.org", password="Test-only-secure-passphrase-2026",
        )
        self.other = User.objects.create_user(
            email="other-viewer@example.org", password="Test-only-other-passphrase-2026",
        )
        country = Country.objects.create(code="GB", name="England")
        league = League.objects.create(country=country, name="Example League")
        club = Club.objects.create(league=league, name="Example FC")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, club_name="Example FC",
            league_name="Example League", country_code="GB",
            title="A Sourced Documentary",
        )
        self.url = reverse("research-job", kwargs={"job_id": self.job.pk})

    def source(self, dossier, url, *, kind="club_official", title="Club history"):
        return SourceReference.objects.create(
            dossier=dossier, url=url, title=title,
            source_kind=kind, access_state="accessible",
            retrieved_at=timezone.now(),
        )

    def seed_dossiers(self):
        first = FactDossier.objects.create(job=self.job, version=1)
        homepage = self.source(first, "https://club.example.org/history")
        fact = Fact.objects.create(
            dossier=first, predicate="founded_year", value=1901,
            assertion_text="The club was founded in 1901.",
        )
        Evidence.objects.create(
            fact=fact, source=homepage,
            locator="History > Foundation",
            summary="The club page gives its early founding date.",
            role=Evidence.Role.UNKNOWN,
        )
        second = fork_dossier(job=self.job, previous=first)
        current = second.facts.get(predicate="founded_year")
        page = second.sources.get(url=homepage.url)
        Evidence.objects.create(
            fact=current, source=page,
            locator="History > Foundation (1901)",
            summary="The dated timeline supports the 1901 foundation year.",
            role=Evidence.Role.SUPPORTS,
        )
        current.verification_state = Fact.Verification.VERIFIED
        current.save(update_fields=["verification_state"])
        FactReview.objects.create(
            fact=current, reviewer=self.owner,
            decision=Fact.Verification.VERIFIED,
            note="The original club timeline was manually checked against the stated founding year.",
            checked_source=True,
        )
        conflict = Fact.objects.create(
            dossier=second, predicate="stadium_name",
            value="Old Stadium",
            assertion_text="The club currently plays at Old Stadium.",
            verification_state=Fact.Verification.CONFLICTED,
        )
        Evidence.objects.create(
            fact=conflict, source=page,
            locator="Club overview > stadium",
            summary="The historical overview lists the original stadium name.",
            role=Evidence.Role.SUPPORTS,
        )
        Evidence.objects.create(
            fact=conflict, source=page,
            locator="Club overview > new stadium",
            summary="A conflicting newer section lists a different ground.",
            role=Evidence.Role.CONTRADICTS,
        )
        FactReview.objects.create(
            fact=conflict, reviewer=self.owner,
            decision=Fact.Verification.CONFLICTED,
            note="Two concrete source sections disagree about the stadium and no reliable resolution exists.",
            checked_source=True,
        )
        return first, second

    def test_no_dossier_returns_explanatory_read_only_page(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Für diesen Job liegt noch kein Faktendossier vor.")
        self.assertContains(response, "nur lesend")
        self.assertContains(response, "Example FC")
        self.assertNotContains(response, "Originalquelle öffnen")
        self.assertEqual(response["Cache-Control"].find("no-store") >= 0, True)
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(FactDossier.objects.count(), 0)

    def test_redirects_anonymous_and_returns_404_for_other_owners(self):
        self.seed_dossiers()
        anonymous = self.client.get(self.url)
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/accounts/login/?next=", anonymous.url)

        self.client.force_login(self.other)
        for url in (self.url, self.url + "?version=1", self.url + "?version=2"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
        self.assertNotIn(b"Example FC", self.client.get(self.url).content)

        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_latest_view_shows_sources_evidence_contradiction_and_review(self):
        v1, v2 = self.seed_dossiers()
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["snapshot"]["version"], 2)
        self.assertEqual(response.context["latest_version"], 2)
        self.assertContains(response, "Version 2")
        self.assertContains(response, "neuester Stand")
        self.assertContains(response, "Offizielle Vereinsseite")
        self.assertContains(response, "https://club.example.org/history")
        self.assertContains(response, "Stützender Beleg")
        self.assertContains(response, "Gegenbeleg / Widerspruch")
        self.assertContains(response, "Widersprüchlich")
        self.assertContains(response, "Verifiziert")
        self.assertContains(response, "Foundation (1901)")
        self.assertContains(response, "Originalquelle öffnen")
        self.assertContains(response, "Die Originalquelle", count=0)
        self.assertContains(
            response, "The original club timeline was manually checked",
        )
        self.assertContains(response, "Prüfer-ID")
        self.assertEqual(response.context["versions"], [2, 1])
        self.assertEqual(FactDossier.objects.count(), 2)
        self.assertEqual(v1.facts.count(), 1)
        self.assertEqual(v2.facts.count(), 2)

    def test_history_shows_old_unverified_fact_without_new_review(self):
        self.seed_dossiers()
        self.client.force_login(self.owner)
        old = self.client.get(self.url + "?version=1")
        self.assertEqual(old.status_code, 200)
        self.assertEqual(old.context["snapshot"]["version"], 1)
        self.assertContains(old, "historischer Stand")
        self.assertContains(old, "Ungeprüft")
        self.assertContains(old, "Noch keine ausdrückliche Prüferentscheidung")
        self.assertNotContains(old, "Widersprüchlich")
        self.assertNotContains(old, "Two concrete source sections disagree")
        self.assertContains(old, 'aria-current="page">Version 1', count=1)
        recent = self.client.get(self.url + "?version=2")
        self.assertEqual(recent.status_code, 200)
        self.assertContains(recent, "Widersprüchlich")

    def test_invalid_missing_and_unknown_versions_are_404(self):
        self.seed_dossiers()
        self.client.force_login(self.owner)
        for value in (
            "0", "-1", "+1", "00", "01", "1.0", "abc", "999",
            "9999999999", "1<script>", "1%2F2", "",
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    self.client.get(self.url, {"version": value}).status_code, 404,
                )
        self.assertEqual(self.client.get(self.url + "?version=1").status_code, 200)

    def test_only_get_allowed_and_no_network_or_database_writes(self):
        self.seed_dossiers()
        self.client.force_login(self.owner)
        baseline = (FactDossier.objects.count(), Fact.objects.count(),
                    Evidence.objects.count(), FactReview.objects.count())
        with patch("urllib.request.urlopen") as net, patch(
            "app.production.safe_official_fetch._download_public_https",
        ) as downloader, patch(
            "app.production.official_site_research.research_official_website",
        ) as research:
            self.assertEqual(self.client.get(self.url).status_code, 200)
            self.assertEqual(self.client.get(self.url + "?version=1").status_code, 200)
            self.assertEqual(self.client.post(self.url, {"decision": "verified"}).status_code, 405)
            self.assertEqual(self.client.put(self.url, data="x", content_type="text/plain").status_code, 405)
            net.assert_not_called()
            downloader.assert_not_called()
            research.assert_not_called()
        self.assertEqual(
            baseline,
            (FactDossier.objects.count(), Fact.objects.count(),
             Evidence.objects.count(), FactReview.objects.count()),
        )

    def test_untrusted_page_text_escaped_and_non_https_not_clickable(self):
        first, _ = self.seed_dossiers()
        malicious = "<script>alert('source')</script>"
        self.source(
            first, "javascript:alert('bad')",
            title=malicious,
        )
        Fact.objects.create(
            dossier=first, predicate="stadium_name", value=malicious,
            assertion_text="<img src=x onerror=alert(1)>",
        )
        self.client.force_login(self.owner)
        response = self.client.get(self.url + "?version=1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script&gt;", html=False)
        self.assertContains(response, "&lt;img src=x onerror=alert(1)&gt;", html=False)
        self.assertNotIn(b"<script>", response.content)
        self.assertNotIn(b"<img src=x", response.content)
        self.assertNotIn(b'href="javascript:', response.content)
        self.assertContains(response, "Nicht als Link freigegeben")

    def test_homepage_contains_link_template_for_job_list(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Recherchedossier ansehen")
        self.assertContains(response, "/jobs/987654321/research/")

    def test_unauthenticated_api_stays_private_and_no_csrf_post_bypass(self):
        self.seed_dossiers()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.get(self.url).status_code, 200)
        # Strict CSRF blocks the request before GET-only method enforcement.
        self.assertEqual(client.post(self.url, {"decision": "verified"}).status_code, 403)
        client.logout()
        self.assertEqual(client.get(self.url).status_code, 302)
