"""P856 suggestions are clickable but never self-approved official sources."""
from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from app.clubs.models import Club, Country, League
from .models import FactDossier, ProductionJob, SourceConfirmation
from .official_source_candidates import proposed_site_for_context
from .test_official_source_candidates import CLUB_SITE, LEAGUE_SITE, CLUB_QID


class OfficialSourceSuggestionsWebTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="p856-web-owner@example.org",
            password="Only-fixture-password-2026",
        )
        self.other = User.objects.create_user(
            email="p856-web-other@example.org",
            password="Only-fixture-password-2026",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club,
            club_name="Sturm Graz", country_code="AT",
            league_name="Austrian Bundesliga",
            title="The Sturm Graz documentary",
        )
        self.dossier = FactDossier.objects.create(job=self.job, version=1)
        from .models import SourceReference
        SourceReference.objects.create(
            dossier=self.dossier, source_kind="wikidata",
            title="[auto] SK Sturm Graz",
            external_id=CLUB_QID,
            url="https://www.wikidata.org/wiki/Special:EntityData/"+CLUB_QID+".json",
            retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
            access_state="accessible",
        )
        self.research = reverse("research-job", kwargs={"job_id": self.job.pk})
        self.form_url = reverse("research-new-source", kwargs={"job_id": self.job.pk})
        self.client.force_login(self.owner)

    def make_suggestions(self):
        from .official_source_candidates import import_official_site_candidates
        with patch(
            "app.production.official_source_candidates.discover_official_site_candidates",
            return_value={
                "club_qid": CLUB_QID, "club_url": CLUB_SITE,
                "league_qid": "Q123789", "league_url": LEAGUE_SITE,
            },
        ):
            return import_official_site_candidates(
                owner=self.owner, job_id=self.job.pk, expected_version=1,
            )

    def test_read_only_dossier_renders_proposals_and_no_confirmations(self):
        self.make_suggestions()
        page = self.client.get(self.research)
        self.assertContains(page, "Automatisch gefundene offizielle Website-Kandidaten")
        self.assertContains(page, CLUB_SITE)
        self.assertContains(page, LEAGUE_SITE)
        self.assertContains(page, "?candidate=club")
        self.assertContains(page, "?candidate=league")
        self.assertContains(page, "weder eine Prüfung der Domain")
        self.assertFalse(SourceConfirmation.objects.exists())
        self.assertEqual(FactDossier.objects.count(), 2)

    def test_candidate_form_prefills_only_url_title_context_never_attestations(self):
        latest = self.make_suggestions()
        response = self.client.get(self.form_url + "?candidate=club")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{CLUB_SITE}"')
        self.assertContains(response, "Offizielle Vereinswebsite")
        self.assertContains(response, 'name="expected_version" value="2"')
        self.assertNotContains(response, 'checked="checked"')
        self.assertNotContains(response, "Wikidata hat die Website verifiziert")
        self.assertFalse(SourceConfirmation.objects.exists())
        self.assertEqual(FactDossier.objects.count(), 2)
        response = self.client.get(self.form_url + "?candidate=league")
        self.assertContains(response, f'value="{LEAGUE_SITE}"')
        self.assertContains(response, 'value="league" selected')
        self.assertIsNotNone(proposed_site_for_context(latest, "league"))

    def test_suggestion_not_sufficient_to_enable_official_autopilot_steps(self):
        latest = self.make_suggestions()
        from .research_autopilot import research_plan
        plan = research_plan(job=self.job, dossier=latest)
        self.assertFalse(plan["complete"])
        self.assertNotEqual(plan["steps"][4]["status"], "ready")
        self.assertNotEqual(plan["steps"][5]["status"], "ready")
        self.assertFalse(SourceConfirmation.objects.exists())

    def test_persisting_source_still_requires_all_manual_checkboxes(self):
        self.make_suggestions()
        post = {
            "expected_version": "2",
            "context": "club", "url": CLUB_SITE,
            "title": "Offizielle Vereinswebsite · Sturm Graz",
            "basis": "I opened the club site and checked its identity and terms.",
            "identity_confirmed": "on",
            "terms_confirmed": "on",
        }
        before = self.client.post(self.form_url, post)
        self.assertEqual(before.status_code, 400)
        self.assertFalse(SourceConfirmation.objects.exists())
        post["access_confirmed"] = "on"
        after = self.client.post(self.form_url, post)
        self.assertEqual(after.status_code, 302)
        self.assertEqual(SourceConfirmation.objects.count(), 1)
        new = FactDossier.objects.get(job=self.job, version=3)
        from .research_autopilot import research_plan
        self.assertTrue(
            any(s.manual_confirmation.reviewer_id == self.owner.pk
                for s in new.sources.filter(source_kind="club_official"))
        )
        self.assertTrue(
            any(s.source_kind == "wikidata" for s in new.sources.all())
        )

    def test_attacker_cannot_prefill_unauthorized_domain_from_query(self):
        self.make_suggestions()
        foreign = self.client.get(
            self.form_url+"?candidate=https://127.0.0.1/",
        )
        self.assertNotContains(foreign, "https://127.0.0.1/")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.form_url+"?candidate=club").status_code, 404)
        self.assertEqual(self.client.get(self.research).status_code, 404)

    def test_no_implicit_permission_on_csrf_protected_post(self):
        self.make_suggestions()
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.owner)
        data = {
            "expected_version": "2", "context": "club",
            "url": CLUB_SITE, "title": "Official football club website",
            "basis": "I checked this club's official homepage by myself.",
            "identity_confirmed": "on", "terms_confirmed": "on",
            "access_confirmed": "on",
        }
        self.assertEqual(secure.post(self.form_url, data).status_code, 403)
        self.assertFalse(SourceConfirmation.objects.exists())
