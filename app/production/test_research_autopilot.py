"""One-click research planner and safe stage chaining, entirely offline."""
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.clubs.models import Club, Country, League
from .models import (
    Fact, FactDossier, ProductionJob, SourceConfirmation,
    SourceReference,
)
from .research_autopilot import execute_next_research, research_plan
from .wikimedia_auto import AutoResearchError


CLUB_QID = "Q124007617"
WD_CLUB = (
    "https://www.wikidata.org/wiki/Special:EntityData/"
    + CLUB_QID + ".json"
)


class ResearchAutopilotServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="autopilot-owner@example.com",
            password="Test-only-owner-123456",
        )
        self.foreign = User.objects.create_user(
            email="autopilot-foreign@example.com",
            password="Test-only-foreign-123456",
        )
        country = Country.objects.create(name="Austria", code="AT")
        league = League.objects.create(
            country=country, name="Austrian Bundesliga",
        )
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club,
            club_name="Sturm Graz",
            country_code="AT",
            league_name="Austrian Bundesliga",
            title="Automated documentary research",
        )

    def dossier(self, version=1):
        return FactDossier.objects.create(
            job=self.job, version=version,
        )

    def source(self, dossier, *, url, kind, title, external_id=""):
        return SourceReference.objects.create(
            dossier=dossier, url=url, source_kind=kind,
            title=title, external_id=external_id,
            retrieved_at=datetime(2026, 11, 13, tzinfo=dt_timezone.utc),
            access_state="accessible",
        )

    def club_identity(self, dossier):
        self.source(
            dossier, url=WD_CLUB, kind="wikidata",
            title="[auto] SK Sturm Graz", external_id=CLUB_QID,
        )

    def confirmed(self, dossier, *, kind, home, host):
        source = self.source(
            dossier, url=home, kind=kind, title="Verified home link",
        )
        SourceConfirmation.objects.create(
            source=source, reviewer=self.owner, confirmed_domain=host,
            checked_at=datetime(2026, 11, 11, tzinfo=dt_timezone.utc),
            identity_confirmed=True, terms_confirmed=True,
            access_confirmed=True,
            basis="Confirmed by this user as an official source website.",
        )

    def stage_markers(self, dossier):
        self.club_identity(dossier)
        self.source(
            dossier, url="https://query.wikidata.org/sparql",
            kind="wikidata", title="P54 discovery",
            external_id="auto-p54:" + CLUB_QID,
        )
        self.source(
            dossier,
            url=WD_CLUB, kind="wikidata",
            title="P856 official-site candidate scan",
            external_id="auto-p856-sites:" + CLUB_QID,
        )
        self.source(
            dossier, url="https://sksturm.at/c/legendenklub",
            kind="club_official", title="[auto] legend roster",
            external_id="auto-official-legends:" + CLUB_QID,
        )
        self.source(
            dossier, url="https://www.bundesliga.at/de/titel-uebersicht",
            kind="league_official", title="[auto] honours",
            external_id="auto-honours:" + CLUB_QID,
        )
        Fact.objects.create(
            dossier=dossier, predicate="stadium_name",
            value="Merkur Arena",
            assertion_text="The home stadium is Merkur Arena.",
        )

    def test_new_club_starts_with_entity_discovery_and_no_manual_data(self):
        plan = research_plan(job=self.job)
        self.assertEqual(plan["next_id"], "club")
        self.assertEqual(plan["version"], 0)
        self.assertEqual(plan["completed"], 0)
        self.assertEqual(
            [item["status"] for item in plan["steps"]],
            ["ready", "waiting", "waiting", "waiting", "waiting", "waiting"],
        )

    def test_after_entity_finds_stadium_and_players_without_manual_links(self):
        dossier = self.dossier()
        self.club_identity(dossier)
        plan = research_plan(job=self.job, dossier=dossier)
        self.assertEqual(plan["next_id"], "stadium")
        self.assertEqual(plan["completed"], 1)
        self.assertEqual(plan["steps"][2]["status"], "ready")
        self.assertEqual(plan["steps"][3]["status"], "waiting")
        self.assertEqual(plan["steps"][5]["status"], "requires_source")

    def test_after_free_steps_no_official_crawl_without_site_confirmation(self):
        dossier = self.dossier()
        self.club_identity(dossier)
        self.source(
            dossier, url="https://query.wikidata.org/sparql",
            kind="wikidata", title="Players",
            external_id="auto-p54:" + CLUB_QID,
        )
        Fact.objects.create(
            dossier=dossier, predicate="stadium_name", value="Merkur Arena",
            assertion_text="Home venue candidate.",
        )
        self.source(
            dossier,
            url=WD_CLUB, kind="wikidata",
            title="P856 official-site candidate scan",
            external_id="auto-p856-sites:" + CLUB_QID,
        )
        # A raw official-looking URL is not consent to fetch it.
        self.source(
            dossier, url="https://sksturm.at/",
            kind="club_official", title="Manually typed homepage",
        )
        plan = research_plan(job=self.job, dossier=dossier)
        self.assertEqual(plan["completed"], 4)
        self.assertIsNone(plan["next_id"])
        self.assertTrue(plan["requires_source"])
        self.assertEqual(plan["steps"][4]["status"], "requires_source")
        self.assertEqual(plan["steps"][5]["status"], "requires_source")

    def test_source_confirmation_enables_both_official_stages(self):
        dossier = self.dossier()
        self.club_identity(dossier)
        self.source(
            dossier, url="https://query.wikidata.org/sparql",
            kind="wikidata", title="Players",
            external_id="auto-p54:" + CLUB_QID,
        )
        Fact.objects.create(
            dossier=dossier, predicate="stadium_name", value="Merkur Arena",
            assertion_text="Home venue candidate.",
        )
        self.source(
            dossier,
            url=WD_CLUB, kind="wikidata",
            title="P856 official-site candidate scan",
            external_id="auto-p856-sites:" + CLUB_QID,
        )
        self.confirmed(
            dossier, kind="club_official",
            home="https://sksturm.at/", host="sksturm.at",
        )
        self.confirmed(
            dossier, kind="league_official",
            home="https://www.bundesliga.at/", host="www.bundesliga.at",
        )
        plan = research_plan(job=self.job, dossier=dossier)
        self.assertEqual(plan["next_id"], "legends")
        self.assertEqual(plan["steps"][4]["status"], "ready")
        self.assertEqual(plan["steps"][5]["status"], "ready")

    def test_complete_existing_sturm_dossier_does_not_query_network(self):
        dossier = self.dossier(version=7)
        self.stage_markers(dossier)
        plan = research_plan(job=self.job, dossier=dossier)
        self.assertTrue(plan["complete"])
        self.assertEqual(plan["completed"], 6)
        self.assertIsNone(plan["next_id"])
        with patch(
            "app.production.wikimedia_auto.import_free_club_research"
        ) as discover:
            answer = execute_next_research(
                owner=self.owner, job=self.job, expected_version=7,
            )
        self.assertIsNone(answer["stage"])
        self.assertEqual(answer["dossier"].pk, dossier.pk)
        discover.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.wikimedia_auto.import_free_club_research")
    def test_one_post_runs_only_first_stage(self, discover):
        def persist(**kwargs):
            self.assertEqual(kwargs["expected_version"], 0)
            dossier = self.dossier()
            self.club_identity(dossier)
            return dossier

        discover.side_effect = persist
        result = execute_next_research(
            owner=self.owner, job=self.job, expected_version=0,
        )
        self.assertEqual(result["stage"], "club")
        self.assertEqual(result["plan"]["next_id"], "stadium")
        self.assertEqual(result["plan"]["version"], 1)
        self.assertEqual(FactDossier.objects.count(), 1)
        discover.assert_called_once_with(
            owner=self.owner, job_id=self.job.pk, expected_version=0,
        )

    @patch("app.production.wikimedia_stadium.enrich_wikimedia_stadium")
    @patch("app.production.wikimedia_auto.import_free_club_research")
    def test_stale_or_foreign_owner_never_calls_any_importer(
        self, discover, stadium,
    ):
        dossier = self.dossier()
        self.club_identity(dossier)
        with self.assertRaisesMessage(AutoResearchError, "stale_dossier"):
            execute_next_research(
                owner=self.owner, job=self.job, expected_version=0,
            )
        with self.assertRaisesMessage(AutoResearchError, "not_authorized"):
            execute_next_research(
                owner=self.foreign, job=self.job, expected_version=1,
            )
        discover.assert_not_called()
        stadium.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.wikimedia_stadium.enrich_wikimedia_stadium")
    def test_failure_preserves_old_version_and_stops_chaining(self, stadium):
        dossier = self.dossier()
        self.club_identity(dossier)
        stadium.side_effect = AutoResearchError("no_stadium_candidate")
        with self.assertRaisesMessage(
            AutoResearchError, "no_stadium_candidate",
        ):
            execute_next_research(
                owner=self.owner, job=self.job, expected_version=1,
            )
        self.assertEqual(FactDossier.objects.count(), 1)

    def test_other_jobs_dossiers_cannot_be_used_to_plan_this_job(self):
        other = ProductionJob.objects.create(
            owner=self.foreign, club=self.job.club, title="Other club job",
            club_name="Sturm Graz", country_code="AT",
            league_name="Bundesliga",
        )
        dossier = FactDossier.objects.create(job=other, version=1)
        with self.assertRaisesMessage(
            ValueError, "does not belong",
        ):
            research_plan(job=self.job, dossier=dossier)
