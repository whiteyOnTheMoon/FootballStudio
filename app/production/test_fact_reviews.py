"""No-network DB tests for explicit human review and conflict-aware dossiers."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from app.clubs.models import Club, Country, League
from .dossiers import load_fact_dossier
from .fact_reviews import append_review_evidence, decide_fact_review
from .models import Evidence, Fact, FactDossier, FactReview, ProductionJob, SourceReference


REASON = (
    "I checked the original source section against the exact claim and "
    "compared the relevant time period before making this review decision."
)


class HumanFactReviewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="review-owner@example.org", password="Only-Test-Passphrase-2026",
        )
        self.other = User.objects.create_user(
            email="review-other@example.org", password="Only-Test-Passphrase-2026",
        )
        country = Country.objects.create(code="GB", name="England")
        league = League.objects.create(country=country, name="Example League")
        club = Club.objects.create(league=league, name="Example Football Club")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, title="Official Fact Review",
            country_code="GB", league_name="Example League",
            club_name="Example Football Club",
        )
        self.original = FactDossier.objects.create(job=self.job, version=1)
        self.club_source = self.source(
            self.original, "https://club.example.org/history",
            SourceReference.Kind.CLUB_OFFICIAL,
        )
        self.league_source = self.source(
            self.original, "https://league.example.org/standings",
            SourceReference.Kind.LEAGUE_OFFICIAL,
        )
        self.wikidata_source = self.source(
            self.original,
            "https://www.wikidata.org/wiki/Special:EntityData/Q123.json",
            SourceReference.Kind.WIKIDATA,
        )
        self.founded = Fact.objects.create(
            dossier=self.original, predicate="founded_year", value=1901,
            assertion_text="The club was established in 1901.",
        )
        self.standings = Fact.objects.create(
            dossier=self.original, predicate="standings_position",
            value={"competition": "Example League", "season": "2025/26", "position": 3},
            assertion_text="The club finished third in Example League in 2025/26.",
        )
        Evidence.objects.create(
            fact=self.founded, source=self.club_source,
            locator="Foundation", summary="Not yet inspected by a reviewer.",
            role=Evidence.Role.UNKNOWN,
        )

    def source(self, dossier, url, kind, *, state="accessible"):
        return SourceReference.objects.create(
            dossier=dossier, url=url, title="Source page",
            source_kind=kind, access_state=state,
            retrieved_at=timezone.now() - timedelta(hours=1),
        )

    def latest(self):
        return FactDossier.objects.filter(job=self.job).order_by("-version").first()

    def at(self, predicate, *, dossier=None):
        dossier = dossier or self.latest()
        return dossier.facts.get(predicate=predicate)

    def cite(self, *, predicate="founded_year", source_url=None,
             role="supports", locator="History > Foundation (1901)",
             summary="The official historical timeline states the foundation year 1901.",
             **changes):
        dossier = self.latest()
        fact = self.at(predicate, dossier=dossier)
        source = dossier.sources.get(url=source_url or self.club_source.url)
        payload = {
            "owner": self.owner, "job_id": self.job.pk,
            "expected_version": dossier.version, "fact_id": fact.pk,
            "source_id": source.pk, "role": role, "locator": locator,
            "summary": summary, "source_checked": True,
        }
        payload.update(changes)
        return append_review_evidence(**payload)

    def decide(self, *, predicate="founded_year", decision="verified",
               source_checked=True, season_checked=False, **changes):
        dossier = self.latest()
        fact = self.at(predicate, dossier=dossier)
        payload = {
            "owner": self.owner, "job_id": self.job.pk,
            "expected_version": dossier.version, "fact_id": fact.pk,
            "decision": decision, "review_note": REASON,
            "review_confirmed": True,
            "source_checked": source_checked,
            "season_checked": season_checked,
        }
        payload.update(changes)
        return decide_fact_review(**payload)

    def test_checked_support_creates_new_version_but_no_automatic_verification(self):
        updated = self.cite()
        self.assertEqual(updated.version, 2)
        self.assertEqual(self.original.facts.count(), 2)
        old_fact = self.at("founded_year", dossier=self.original)
        self.assertEqual(old_fact.evidence.count(), 1)
        self.assertEqual(old_fact.verification_state, "unverified")
        fact = self.at("founded_year")
        self.assertEqual(fact.verification_state, "unverified")
        self.assertFalse(FactReview.objects.exists())
        support = fact.evidence.get(role="supports")
        self.assertEqual(support.source.dossier_id, updated.pk)
        self.assertEqual(support.fact_id, fact.pk)
        self.assertEqual(support.locator, "History > Foundation (1901)")
        self.assertEqual(len(fact.evidence.all()), 2)

    def test_verified_requires_review_confirmation_and_real_checked_support(self):
        before = self.latest()
        with self.assertRaisesRegex(ValueError, "supporting locator"):
            self.decide()
        with self.assertRaisesRegex(ValueError, "confirmation"):
            self.decide(review_confirmed=False)
        self.cite()
        with self.assertRaisesRegex(ValueError, "confirmation"):
            self.decide(review_confirmed=1)
        with self.assertRaisesRegex(ValueError, "checked accessible"):
            self.decide(source_checked=False)
        self.assertEqual(self.latest().version, 2)
        reviewed = self.decide()
        self.assertEqual(reviewed.version, 3)
        self.assertEqual(self.at("founded_year").verification_state, "verified")
        self.assertEqual(self.at("founded_year", dossier=before).verification_state,
                         "unverified")
        saved = FactReview.objects.get(fact=self.at("founded_year"))
        self.assertEqual(saved.reviewer_id, self.owner.pk)
        self.assertEqual(saved.decision, "verified")
        self.assertEqual(saved.note, REASON)
        self.assertTrue(saved.checked_source)
        self.assertFalse(saved.checked_season)
        self.assertLess((timezone.now() - saved.reviewed_at).total_seconds(), 60)
        snapshot = load_fact_dossier(
            owner=self.owner, job_id=self.job.pk, version=3,
        )
        record = next(f for f in snapshot["facts"] if f["predicate"] == "founded_year")
        self.assertEqual(record["review"]["decision"], "verified")
        self.assertEqual(record["review"]["reviewer_id"], self.owner.pk)
        self.assertTrue(record["review"]["checked_source"])
        self.assertIn("reviewed_at", record["review"])
        prior = load_fact_dossier(owner=self.owner, job_id=self.job.pk, version=2)
        earlier = next(f for f in prior["facts"] if f["predicate"] == "founded_year")
        self.assertIsNone(earlier["review"])

    def test_existing_review_is_inherited_on_new_unrelated_fact_version(self):
        self.cite()
        reviewed = self.decide()
        first_review = self.at("founded_year").review
        newer = self.cite(
            predicate="standings_position",
            source_url=self.league_source.url,
            locator="2025/26 > Final table",
            summary="The competition standings for 2025/26 list the club third.",
        )
        self.assertEqual(newer.version, reviewed.version + 1)
        old_fact = self.at("founded_year", dossier=reviewed)
        new_fact = self.at("founded_year", dossier=newer)
        self.assertEqual(new_fact.verification_state, "verified")
        self.assertNotEqual(new_fact.pk, old_fact.pk)
        self.assertEqual(new_fact.review.reviewed_at, first_review.reviewed_at)
        self.assertEqual(new_fact.review.note, first_review.note)
        self.assertEqual(new_fact.review.reviewer_id, self.owner.pk)
        for item in new_fact.evidence.all():
            self.assertEqual(item.source.dossier_id, newer.pk)

    def test_editing_evidence_after_verified_invalidates_new_version_review(self):
        self.cite()
        verified = self.decide()
        prior_review_pk = self.at("founded_year", dossier=verified).review.pk
        next_dossier = self.cite(
            role="context_only", locator="History > Additional context",
            summary="A secondary section contains background on the club.",
        )
        self.assertEqual(next_dossier.version, verified.version + 1)
        old_fact = self.at("founded_year", dossier=verified)
        new_fact = self.at("founded_year", dossier=next_dossier)
        self.assertEqual(old_fact.verification_state, "verified")
        self.assertEqual(old_fact.review.pk, prior_review_pk)
        self.assertEqual(new_fact.verification_state, "unverified")
        self.assertFalse(FactReview.objects.filter(fact=new_fact).exists())
        self.assertIsNone(load_fact_dossier(
            owner=self.owner, job_id=self.job.pk, version=next_dossier.version,
        )["facts"][0]["review"])

    def test_unresolved_contradictory_evidence_blocks_verified(self):
        self.cite()
        self.cite(
            source_url=self.wikidata_source.url, role="contradicts",
            locator="P571 > Inception value",
            summary="The second source reports a conflicting foundation year 1902.",
        )
        self.assertEqual(self.latest().version, 3)
        with self.assertRaisesRegex(ValueError, "Unresolved contradictory"):
            self.decide()
        self.assertEqual(self.latest().version, 3)
        with self.assertRaisesRegex(ValueError, "contradictions"):
            self.decide(decision="insufficient_sources")
        decided = self.decide(decision="conflicted")
        self.assertEqual(decided.version, 4)
        self.assertEqual(self.at("founded_year").verification_state, "conflicted")
        self.assertEqual(self.at("founded_year").review.decision, "conflicted")
        self.assertIsNone(FactReview.objects.filter(fact=self.founded).first())
        self.assertEqual(
            self.at("founded_year", dossier=decided).evidence.filter(
                role="contradicts",
            ).count(), 1,
        )

    def test_conflicted_needs_support_contradiction_and_explicit_inspection(self):
        self.cite()
        with self.assertRaisesRegex(ValueError, "supporting AND contradicting"):
            self.decide(decision="conflicted")
        self.cite(
            role="contradicts",
            locator="Club history > Alternative founding year",
            summary="Another section disputes the founding year shown on the page.",
        )
        with self.assertRaisesRegex(ValueError, "checked supporting"):
            self.decide(decision="conflicted", source_checked=False)
        self.assertEqual(self.decide(decision="conflicted").version, 4)

    def test_season_claim_requires_matching_cited_season_and_manual_cross_check(self):
        self.cite(
            predicate="standings_position",
            source_url=self.league_source.url,
            locator="League > 2024/25 table",
            summary="The historical 2024/25 ranking contains a different season.",
        )
        with self.assertRaisesRegex(ValueError, "season cross-check"):
            self.decide(predicate="standings_position", season_checked=False)
        with self.assertRaisesRegex(ValueError, "specific season"):
            self.decide(predicate="standings_position", season_checked=True)
        self.cite(
            predicate="standings_position",
            source_url=self.league_source.url,
            locator="League > 2025/26 final table",
            summary="The official league 2025/26 final table lists third place.",
        )
        # The old 2024/25 reference is STILL present and is still marked
        # supporting. A new 2025/26 source cannot silently override it.
        with self.assertRaisesRegex(ValueError, "specific season"):
            self.decide(predicate="standings_position", season_checked=True)
        self.assertEqual(self.at("standings_position").verification_state, "unverified")

    def test_matching_season_can_be_verified_after_explicit_cross_check(self):
        self.cite(
            predicate="standings_position",
            source_url=self.league_source.url,
            locator="League > 2025/26 final table",
            summary="The official 2025/26 league table shows the club third.",
        )
        with self.assertRaisesRegex(ValueError, "season cross-check"):
            self.decide(predicate="standings_position", season_checked=False)
        new = self.decide(predicate="standings_position", season_checked=True)
        self.assertEqual(self.at("standings_position", dossier=new).verification_state,
                         "verified")
        self.assertTrue(self.at("standings_position", dossier=new).review.checked_season)

    def test_rejected_and_insufficient_have_rationales_but_are_never_verified(self):
        insufficient = self.decide(
            decision="insufficient_sources", source_checked=False,
            review_note="I cannot confirm the foundation year because the available locator is not sufficient.",
        )
        self.assertEqual(insufficient.version, 2)
        self.assertEqual(self.at("founded_year").verification_state,
                         "insufficient_sources")
        rejected = self.decide(
            decision="rejected", source_checked=False,
            review_note="The proposed claim is not supported and will not be used in the script.",
        )
        self.assertEqual(rejected.version, 3)
        self.assertEqual(self.at("founded_year").review.decision, "rejected")
        self.assertEqual(self.at("founded_year", dossier=insufficient).review.decision,
                         "insufficient_sources")

    def test_idempotent_evidence_and_review_do_not_fork_new_dossier(self):
        first = self.cite()
        snapshot = first
        # Exact same evidence in the selected current snapshot.
        source = snapshot.sources.get(url=self.club_source.url)
        fact = self.at("founded_year", dossier=snapshot)
        again = append_review_evidence(
            owner=self.owner, job_id=self.job.pk, expected_version=snapshot.version,
            fact_id=fact.pk, source_id=source.pk,
            role="supports", locator="History > Foundation (1901)",
            summary="The official historical timeline states the foundation year 1901.",
            source_checked=True,
        )
        self.assertEqual(first.pk, again.pk)
        decision = self.decide()
        reviewed_fact = self.at("founded_year", dossier=decision)
        repeated = decide_fact_review(
            owner=self.owner, job_id=self.job.pk, expected_version=decision.version,
            fact_id=reviewed_fact.pk, decision="verified",
            review_note=REASON, review_confirmed=True,
            source_checked=True, season_checked=False,
        )
        self.assertEqual(repeated.pk, decision.pk)
        self.assertEqual(self.latest().version, 3)

    def test_stale_versions_and_cross_owner_fact_source_ids_cannot_mutate(self):
        self.cite()
        old_version, old_fact, old_source = (
            self.original.version, self.founded.pk, self.club_source.pk,
        )
        count = FactDossier.objects.count()
        with self.assertRaisesRegex(ValueError, "Stale dossier"):
            append_review_evidence(
                owner=self.owner, job_id=self.job.pk, expected_version=old_version,
                fact_id=old_fact, source_id=old_source,
                role="supports", locator="History > Foundation",
                summary="The official section states the foundation year.",
                source_checked=True,
            )
        with self.assertRaisesRegex(ValueError, "Stale dossier"):
            self.decide(expected_version=old_version)
        with self.assertRaises(ProductionJob.DoesNotExist):
            self.cite(owner=self.other)
        with self.assertRaises(ProductionJob.DoesNotExist):
            self.decide(owner=self.other)
        from django.core.exceptions import ObjectDoesNotExist
        with self.assertRaises(ObjectDoesNotExist):
            self.cite(source_id=old_source)
        with self.assertRaises(ObjectDoesNotExist):
            self.decide(fact_id=old_fact)
        self.assertEqual(FactDossier.objects.count(), count)

    def test_evidence_from_another_dossier_and_restricted_source_are_rejected(self):
        other_job = ProductionJob.objects.create(
            owner=self.other, club=self.job.club, title="Other owner",
            country_code="GB", league_name="Example League", club_name="Example Football Club",
        )
        other_dossier = FactDossier.objects.create(job=other_job, version=1)
        other_source = self.source(
            other_dossier, "https://other.example.org/history",
            SourceReference.Kind.CLUB_OFFICIAL,
        )
        with self.assertRaises(SourceReference.DoesNotExist):
            self.cite(source_id=other_source.pk)
        self.club_source.access_state = "restricted"
        self.club_source.save(update_fields=["access_state"])
        with self.assertRaisesRegex(ValueError, "accessible"):
            self.cite()
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 1)

    def test_unsafe_unconfirmed_evidence_and_reviews_fail_closed(self):
        for changes in (
            {"role": "unknown"},
            {"role": "verified"},
            {"source_checked": False},
            {"source_checked": 1},
            {"source_id": 0},
            {"source_id": True},
            {"expected_version": False},
            {"locator": ""},
            {"locator": "A" * 181},
            {"summary": "short"},
            {"summary": "<script>not allowed content</script>"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.cite(**changes)
        for changes in (
            {"review_confirmed": False},
            {"review_confirmed": 1},
            {"decision": "unverified"},
            {"decision": "made_up"},
            {"review_note": "short"},
            {"review_note": "<script>unsafe review note</script>" + " " * 35},
            {"source_checked": 1},
            {"season_checked": "yes"},
            {"expected_version": True},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.decide(**changes)
        self.assertEqual(FactDossier.objects.filter(job=self.job).count(), 1)

    def test_model_review_cannot_be_forged_by_foreign_user_or_status_mismatch(self):
        fact = self.founded
        with self.assertRaises(ValidationError):
            FactReview.objects.create(
                fact=fact, reviewer=self.other,
                decision="verified", note=REASON,
            )
        with self.assertRaises(ValidationError):
            FactReview.objects.create(
                fact=fact, reviewer=self.owner,
                decision="verified", note=REASON,
            )
        self.assertFalse(FactReview.objects.exists())

    @patch("urllib.request.urlopen")
    @patch("app.production.safe_official_fetch._download_public_https")
    def test_human_review_never_fetches_source_urls(self, download, urllib):
        self.cite()
        self.decide()
        download.assert_not_called()
        urllib.assert_not_called()
