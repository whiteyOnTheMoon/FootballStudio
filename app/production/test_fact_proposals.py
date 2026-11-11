"""Offline/DB regression tests for owner-scoped sourced atomic fact proposals."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from app.clubs.models import Club, Country, League

from .dossiers import load_fact_dossier
from .fact_proposals import propose_official_fact
from .models import Evidence, Fact, FactDossier, ProductionJob, SourceReference


class OfficialFactProposalsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="fact-proposer@example.org", password="example-long-pass-2026",
        )
        self.other = User.objects.create_user(
            email="fact-intruder@example.org", password="example-long-pass-2026",
        )
        country = Country.objects.create(code="GB", name="England")
        league = League.objects.create(country=country, name="Example League")
        club = Club.objects.create(league=league, name="Example FC")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, title="A sourced documentary",
            country_code="GB", league_name="Example League", club_name="Example FC",
        )
        self.first = FactDossier.objects.create(job=self.job, version=1)
        self.club_source = self.source(
            self.first, "https://club.example.org/history",
            SourceReference.Kind.CLUB_OFFICIAL,
        )
        self.league_source = self.source(
            self.first, "https://league.example.org/standings",
            SourceReference.Kind.LEAGUE_OFFICIAL,
        )
        self.wikidata_source = self.source(
            self.first, "https://www.wikidata.org/wiki/Special:EntityData/Q123.json",
            SourceReference.Kind.WIKIDATA,
        )

    def source(self, dossier, url, kind, *, status="accessible"):
        return SourceReference.objects.create(
            dossier=dossier, url=url, source_kind=kind,
            title="Official page", retrieved_at=timezone.now() - timedelta(hours=1),
            access_state=status,
        )

    def submit(self, **kwargs):
        data = {
            "owner": self.owner,
            "job_id": self.job.pk,
            "expected_version": 1,
            "source_id": self.club_source.pk,
            "predicate": "founded_year",
            "value": 1901,
            "assertion_text": "The club was founded in 1901.",
            "locator": "History > Foundation section",
            "evidence_summary": "The dated foundation is mentioned in the club history.",
        }
        data.update(kwargs)
        return propose_official_fact(**data)

    def test_new_proposal_has_source_locator_and_never_verifies_itself(self):
        new = self.submit()
        self.assertEqual(new.version, 2)
        self.assertEqual(self.first.version, 1)
        self.assertEqual(self.first.facts.count(), 0)
        self.assertEqual(new.sources.count(), 3)
        self.assertEqual(new.facts.count(), 1)
        fact = new.facts.get()
        self.assertEqual(fact.predicate, "founded_year")
        self.assertEqual(fact.value, 1901)
        self.assertEqual(fact.verification_state, Fact.Verification.UNVERIFIED)
        evidence = fact.evidence.get()
        self.assertEqual(evidence.role, Evidence.Role.UNKNOWN)
        self.assertEqual(evidence.source.dossier_id, new.pk)
        self.assertNotEqual(evidence.source_id, self.club_source.pk)
        self.assertEqual(evidence.source.url, self.club_source.url)
        self.assertEqual(evidence.locator, "History > Foundation section")
        self.assertEqual(
            evidence.summary, "The dated foundation is mentioned in the club history.",
        )
        snapshot = load_fact_dossier(
            owner=self.owner, job_id=self.job.pk, version=2,
        )
        self.assertEqual(snapshot["facts"][0]["verification_state"], "unverified")
        self.assertEqual(snapshot["facts"][0]["evidence"][0]["role"], "unknown")

    def test_idempotent_repeat_of_same_proposal_and_source_id(self):
        first = self.submit()
        second = self.submit()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(FactDossier.objects.count(), 2)
        self.assertEqual(Fact.objects.count(), 1)
        self.assertEqual(Evidence.objects.count(), 1)

    def test_league_standings_require_explicit_season(self):
        snapshot = self.submit(
            source_id=self.league_source.pk,
            predicate="standings_position",
            value={"competition": "Example League", "season": "2025/26", "position": 3},
            assertion_text="Example FC finished third in the 2025/26 Example League.",
            locator="2025/26 > final league table",
            evidence_summary="The final season table lists the club third.",
        )
        fact = snapshot.facts.get()
        self.assertEqual(fact.value["season"], "2025/26")
        self.assertEqual(fact.value["position"], 3)
        self.assertEqual(fact.verification_state, "unverified")

    def test_competition_win_and_league_membership_are_structured(self):
        options = [
            ("competition_win", {"competition": "National Cup", "season": "2011/12"}),
            ("league_membership", {"league": "Example League", "season": "2024"}),
            ("stadium_name", "Sample Stadium"),
        ]
        for predicate, value in options:
            with self.subTest(predicate=predicate):
                snapshot = self.submit(
                    predicate=predicate, value=value,
                    assertion_text=f"This club has a researched {predicate} record.",
                )
                self.assertEqual(snapshot.facts.last().value, value)
                # Next iteration starts from fresh original dossier.
                FactDossier.objects.filter(job=self.job).exclude(pk=self.first.pk).delete()

    def test_stale_dossier_changes_are_rejected_without_db_writes(self):
        self.submit()
        counts = (
            FactDossier.objects.count(), SourceReference.objects.count(),
            Fact.objects.count(), Evidence.objects.count(),
        )
        with self.assertRaisesRegex(ValueError, "Stale dossier"):
            self.submit(
                value=1902, assertion_text="The club was founded in 1902.",
            )
        self.assertEqual(counts, (
            FactDossier.objects.count(), SourceReference.objects.count(),
            Fact.objects.count(), Evidence.objects.count(),
        ))

    def test_current_new_version_can_be_used_for_next_fact(self):
        version_two = self.submit()
        new_source = version_two.sources.get(url=self.league_source.url)
        version_three = self.submit(
            expected_version=2, source_id=new_source.pk,
            predicate="league_membership",
            value={"league": "Example League", "season": "2025/26"},
            assertion_text="The club played in Example League in 2025/26.",
        )
        self.assertEqual(version_three.version, 3)
        self.assertEqual(self.first.facts.count(), 0)
        self.assertEqual(version_two.facts.count(), 1)
        self.assertEqual(version_three.facts.count(), 2)
        self.assertEqual(version_three.facts.filter(verification_state="verified").count(), 0)
        for fact in version_three.facts.all():
            for ev in fact.evidence.all():
                self.assertEqual(ev.source.dossier_id, version_three.pk)

    def test_owner_and_source_id_are_enforced(self):
        from django.core.exceptions import ObjectDoesNotExist
        bad = [
            {"owner": self.other},
            {"source_id": self.wikidata_source.pk},
            {"source_id": 9999999},
            {"source_id": 0},
            {"source_id": True},
            {"source_id": "123"},
        ]
        for payload in bad:
            with self.subTest(payload=payload):
                with self.assertRaises((ValueError, ObjectDoesNotExist)):
                    self.submit(**payload)
                self.assertEqual(FactDossier.objects.count(), 1)
        other = ProductionJob.objects.create(
            owner=self.other, club=self.job.club, title="Other owner story",
            country_code="GB", league_name="Example League", club_name="Example FC",
        )
        dossier = FactDossier.objects.create(job=other, version=1)
        foreign = self.source(
            dossier, "https://other.example.org/official",
            SourceReference.Kind.CLUB_OFFICIAL,
        )
        with self.assertRaises(SourceReference.DoesNotExist):
            self.submit(source_id=foreign.pk)

    def test_inaccessible_source_rejected_without_new_version(self):
        self.club_source.access_state = SourceReference.Access.RESTRICTED
        self.club_source.save(update_fields=["access_state"])
        with self.assertRaisesRegex(ValueError, "accessible official"):
            self.submit()
        self.assertEqual(FactDossier.objects.count(), 1)

    def test_strict_facts_reject_ambiguous_or_bad_date_and_markup(self):
        bad = [
            {"predicate": "founded_year", "value": True},
            {"predicate": "founded_year", "value": 2050},
            {"predicate": "founded_year", "value": "1901"},
            {"predicate": "stadium_name", "value": "<script>alert(1)</script>"},
            {"predicate": "founded_year", "value": [1901]},
            {"predicate": "market_value", "value": 100000000},
            {"predicate": "competition_win", "value": {"competition": "Cup"}},
            {"predicate": "league_membership", "value": {"league": "National", "season": "2025/29"}},
            {"predicate": "standings_position", "value": {
                "competition": "Example", "season": "2025/26", "position": True,
            }},
            {"predicate": "standings_position", "value": {
                "competition": "Example", "season": "2025/26", "position": 0,
            }},
            {"predicate": "standings_position", "value": {
                "competition": "Example", "season": "2025/26", "position": 6,
                "inject": "ignore me",
            }},
            {"assertion_text": "Tiny"},
            {"assertion_text": "A" * 351},
            {"locator": ""},
            {"locator": "A" * 181},
            {"evidence_summary": "A" * 351},
            {"evidence_summary": "Too short"},
            {"evidence_summary": "<img src=malicious> and other text"},
            {"expected_version": 0},
            {"expected_version": True},
        ]
        for payload in bad:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.submit(**payload)
                self.assertEqual(FactDossier.objects.count(), 1)
                self.assertFalse(Fact.objects.exists())

    @patch("urllib.request.urlopen")
    def test_submission_does_not_call_network(self, opener):
        self.submit()
        opener.assert_not_called()
