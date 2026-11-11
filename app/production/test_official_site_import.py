"""Offline persistence regression tests for official club/league source snapshots."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.clubs.models import Club, Country, League
from .dossiers import load_fact_dossier
from .models import (
    Evidence, Fact, FactDossier, ProductionJob, SourceReference,
)
from .official_site_import import import_official_site_sources
from .safe_official_fetch import WebsiteFetchError


class OfficialSourceImportTests(TestCase):
    CLUB_HOME = "https://club.example.org/en/"
    LEAGUE_HOME = "https://league.example.org/en/"

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="dossier-owner@example.org",
            password="Test-only-Long-Secret-2026",
        )
        self.other = User.objects.create_user(
            email="dossier-other@example.org",
            password="Test-only-Long-Secret-2026",
        )
        country = Country.objects.create(code="GB", name="England")
        league = League.objects.create(country=country, name="Example League")
        club = Club.objects.create(league=league, name="Example Football Club")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, title="Official Source Story",
            country_code="GB", league_name="Example League",
            club_name="Example Football Club",
        )

    def sample(self, *, context="club", homepage=None, subpages=2):
        homepage = homepage or (
            self.CLUB_HOME if context == "club" else self.LEAGUE_HOME
        )
        host = homepage.split("/")[2]
        category = "history" if context == "club" else "standings"
        now = datetime.now(timezone.utc).isoformat()
        pages = [{
            "url": homepage, "title": "Official homepage",
            "headings": ["Welcome"], "retrieved_at": now,
            "verification_state": "unverified",
        }]
        for i in range(subpages):
            pages.append({
                "url": f"https://{host}/{category}/{i}",
                "title": f"{category.title()} {i}",
                "headings": [f"Section {i}"],
                "retrieved_at": now,
                "verification_state": "unverified",
                "category": category,
            })
        return {
            "job_id": self.job.pk, "club_id": self.job.club_id,
            "league_id": self.job.club.league_id,
            "context": context, "site_url": homepage,
            "robots_url": f"https://{host}/robots.txt",
            "source_status": "unverified", "stored": False,
            "pages": pages,
        }

    def do_import(self, **kwargs):
        data = {
            "owner": self.owner, "job_id": self.job.pk,
            "homepage_url": self.CLUB_HOME, "context": "club",
            "identity_confirmed": True, "terms_confirmed": True,
        }
        data.update(kwargs)
        return import_official_site_sources(**data)

    @patch("app.production.official_site_import.research_official_website")
    def test_club_import_creates_only_accessible_source_references(self, research):
        research.return_value = self.sample()
        dossier = self.do_import()
        self.assertEqual(dossier.version, 1)
        self.assertEqual(dossier.sources.count(), 3)
        self.assertFalse(Fact.objects.exists())
        source = dossier.sources.get(url=self.CLUB_HOME)
        self.assertEqual(source.source_kind, SourceReference.Kind.CLUB_OFFICIAL)
        self.assertEqual(source.title, "Official homepage")
        self.assertEqual(source.access_state, SourceReference.Access.ACCESSIBLE)
        self.assertEqual(source.external_id, "")
        self.assertIsNotNone(source.retrieved_at.tzinfo)
        snapshot = load_fact_dossier(
            owner=self.owner, job_id=self.job.pk, version=1,
        )
        self.assertEqual(snapshot["facts"], [])
        self.assertEqual(len(snapshot["sources"]), 3)
        self.assertEqual(
            [s["source_kind"] for s in snapshot["sources"]],
            ["club_official"] * 3,
        )
        self.assertNotIn("headings", snapshot["sources"][0])
        research.assert_called_once_with(
            owner=self.owner, job_id=self.job.pk, homepage_url=self.CLUB_HOME,
            context="club", identity_confirmed=True, terms_confirmed=True,
        )

    @patch("app.production.official_site_import.research_official_website")
    def test_same_homepage_is_idempotent_without_another_request(self, research):
        research.return_value = self.sample()
        first = self.do_import()
        second = self.do_import()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(FactDossier.objects.count(), 1)
        self.assertEqual(SourceReference.objects.count(), 3)
        research.assert_called_once()

    @patch("app.production.official_site_import.research_official_website")
    def test_league_import_clones_old_sources_facts_and_evidence(self, research):
        research.return_value = self.sample()
        first = self.do_import()
        history = first.sources.get(url=f"https://club.example.org/history/0")
        fact = Fact.objects.create(
            dossier=first, predicate="stadium_name", value="Sample Ground",
            assertion_text="The club plays at Sample Ground.",
        )
        Evidence.objects.create(
            fact=fact, source=history, locator="Club history",
            summary="Evidence summary written by reviewer",
            role=Evidence.Role.SUPPORTS,
        )
        # This is a pre-existing reviewed fact, NOT one verified by importing
        # the league website. Its evidence must remain valid in new snapshots.
        fact.verification_state = Fact.Verification.VERIFIED
        fact.save(update_fields=["verification_state"])

        research.return_value = self.sample(
            context="league", homepage=self.LEAGUE_HOME, subpages=1,
        )
        second = self.do_import(
            context="league", homepage_url=self.LEAGUE_HOME,
        )
        self.assertEqual((first.version, second.version), (1, 2))
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.sources.count(), 3)
        self.assertEqual(first.facts.count(), 1)
        self.assertEqual(second.sources.count(), 5)
        self.assertEqual(
            second.sources.filter(source_kind="league_official").count(), 2,
        )
        self.assertEqual(
            second.sources.filter(source_kind="club_official").count(), 3,
        )
        new_fact = second.facts.get()
        self.assertEqual(new_fact.verification_state, Fact.Verification.VERIFIED)
        self.assertNotEqual(fact.pk, new_fact.pk)
        new_evidence = new_fact.evidence.get()
        self.assertEqual(new_evidence.fact.dossier_id, second.pk)
        self.assertEqual(new_evidence.source.dossier_id, second.pk)
        self.assertEqual(new_evidence.summary, "Evidence summary written by reviewer")
        self.assertEqual(history.dossier_id, first.pk)
        self.assertEqual(
            self.do_import(context="league", homepage_url=self.LEAGUE_HOME).pk,
            second.pk,
        )
        self.assertEqual(research.call_count, 2)

    @patch("app.production.official_site_import.research_official_website")
    def test_unauthorized_unconfirmed_and_invalid_host_stop_before_research(self, research):
        for options in (
            {"owner": self.other},
            {"identity_confirmed": False},
            {"identity_confirmed": 1},
            {"terms_confirmed": False},
            {"terms_confirmed": "yes"},
            {"context": "transfermarkt"},
            {"homepage_url": "http://club.example.org/en/"},
            {"homepage_url": "https://127.0.0.1/"},
        ):
            with self.subTest(options=options):
                with self.assertRaises(
                    (ProductionJob.DoesNotExist, ValueError, WebsiteFetchError)
                ):
                    self.do_import(**options)
        research.assert_not_called()
        self.assertFalse(FactDossier.objects.exists())

    @patch("app.production.official_site_import.research_official_website")
    def test_bad_research_response_is_never_persisted(self, research):
        good = self.sample()
        cases = [
            {"job_id": 99999},
            {"club_id": 99999},
            {"league_id": 99999},
            {"context": "league"},
            {"site_url": "https://evil.example.org/"},
            {"source_status": "verified"},
            {"stored": True},
            {"robots_url": "https://evil.example.org/robots.txt"},
            {"pages": []},
            {"pages": good["pages"] * 2},
            {"pages": [good["pages"][0], good["pages"][0]]},
            {"pages": [{**good["pages"][0], "url": "https://evil.example.org/"}]},
            {"pages": [{**good["pages"][0], "title": "A" * 161}]},
            {"pages": [{**good["pages"][0], "retrieved_at": "2026-01-01T00:00:00Z"}]},
            {"pages": [{**good["pages"][0], "retrieved_at": "invalid"}]},
            {"pages": [{**good["pages"][0], "verification_state": "verified"}]},
            {"pages": [good["pages"][0], {
                **good["pages"][1], "category": "untrusted",
            }]},
        ]
        for replacement in cases:
            with self.subTest(replacement=list(replacement)):
                research.return_value = {**good, **replacement}
                with self.assertRaises(WebsiteFetchError) as exc:
                    self.do_import()
                self.assertEqual(exc.exception.code, "invalid_snapshot")
                self.assertFalse(FactDossier.objects.exists())
                self.assertFalse(SourceReference.objects.exists())

    @patch("app.production.official_site_import.research_official_website")
    def test_crawl_errors_leave_existing_dossier_untouched(self, research):
        existing = FactDossier.objects.create(job=self.job, version=1)
        existing_source = SourceReference.objects.create(
            dossier=existing,
            url="https://www.wikidata.org/wiki/Special:EntityData/Q123.json",
            source_kind=SourceReference.Kind.WIKIDATA,
            external_id="Q123", title="Wikidata Q123",
            retrieved_at=datetime.now(timezone.utc),
            access_state=SourceReference.Access.ACCESSIBLE,
        )
        research.side_effect = WebsiteFetchError("robots_disallowed")
        with self.assertRaises(WebsiteFetchError):
            self.do_import()
        self.assertEqual(FactDossier.objects.count(), 1)
        self.assertEqual(SourceReference.objects.count(), 1)
        self.assertEqual(existing_source.dossier_id, existing.pk)

    @patch("app.production.official_site_import.research_official_website")
    def test_same_url_different_source_kind_is_rejected(self, research):
        previous = FactDossier.objects.create(job=self.job, version=1)
        SourceReference.objects.create(
            dossier=previous, url=self.CLUB_HOME,
            source_kind=SourceReference.Kind.OTHER,
            retrieved_at=datetime.now(timezone.utc),
            access_state=SourceReference.Access.ACCESSIBLE,
        )
        with self.assertRaises(ValueError):
            self.do_import()
        research.assert_not_called()
        self.assertEqual(FactDossier.objects.count(), 1)

    @patch("app.production.official_site_import.research_official_website")
    def test_source_collision_during_new_version_is_atomic(self, research):
        previous = FactDossier.objects.create(job=self.job, version=1)
        SourceReference.objects.create(
            dossier=previous, url="https://club.example.org/history/0",
            source_kind=SourceReference.Kind.OTHER,
            retrieved_at=datetime.now(timezone.utc),
            access_state=SourceReference.Access.ACCESSIBLE,
        )
        research.return_value = self.sample()
        with self.assertRaises(ValueError):
            self.do_import()
        self.assertEqual(FactDossier.objects.count(), 1)
        self.assertEqual(SourceReference.objects.count(), 1)

    @patch("app.production.official_site_import.research_official_website")
    def test_foreign_owner_cannot_read_new_dossier(self, research):
        research.return_value = self.sample(subpages=0)
        dossier = self.do_import()
        with self.assertRaises(FactDossier.DoesNotExist):
            load_fact_dossier(
                owner=self.other, job_id=self.job.pk, version=dossier.version,
            )

    @patch("app.production.official_site_import.research_official_website")
    def test_excessive_future_timestamp_fails_closed(self, research):
        sample = self.sample(subpages=0)
        sample["pages"][0]["retrieved_at"] = (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).isoformat()
        research.return_value = sample
        with self.assertRaises(WebsiteFetchError):
            self.do_import()
        self.assertFalse(FactDossier.objects.exists())
