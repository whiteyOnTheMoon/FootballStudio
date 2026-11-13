"""FS-018: source agreement is a research signal, never automatic human review."""
from copy import deepcopy
from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from app.clubs.models import Club, Country, League
from .film_claim_assessment import assess_research_snapshot
from .models import (
    Evidence, Fact, FactDossier, FactReview, ProductionJob, SourceReference,
)

QID = "Q124007617"
LEAGUE = "https://www.bundesliga.at/de/titel-uebersicht"
CLUB = "https://sksturm.at/en/c/steckbrief"


def example():
    return {
        "job_id": 1, "club_name": "Sturm Graz", "version": 7,
        "sources": [
            {
                "id": 11, "source_kind": "league_official",
                "url": LEAGUE, "external_id": "auto-honours:" + QID,
                "access_state": "accessible",
            },
            {
                "id": 12, "source_kind": "club_official",
                "url": CLUB, "external_id": "auto-honours-club:" + QID,
                "access_state": "accessible",
            },
        ],
        "facts": [{
            "id": 21, "predicate": "club_honour_candidate",
            "verification_state": "unverified",
            "review": None,
            "value": {
                "season": "2023/24",
                "category": "domestic_cup",
                "corroboration": "both",
            },
            "evidence": [
                {
                    "source_id": 11, "role": "unknown",
                    "locator": "Season 2023/24 · Cup-Sieger",
                },
                {
                    "source_id": 12, "role": "unknown",
                    "locator": "National success · 2023/24 · domestic_cup",
                },
            ],
        }],
    }


class MachineSourceAssessmentTests(SimpleTestCase):
    def report(self, mutate=None):
        data = example()
        if mutate:
            mutate(data)
        original = deepcopy(data)
        report = assess_research_snapshot(data)
        self.assertEqual(data, original, "Machine assessment must not edit dossiers.")
        self.assertFalse(report["approved_for_voiceover"])
        self.assertTrue(report["no_human_reviews_created"])
        self.assertEqual(report["mode"], "machine_source_assessment_only")
        return report

    def test_two_official_domains_match_without_becoming_human_verified(self):
        report = self.report()
        self.assertEqual(report["counts"]["matching_records"], 1)
        item = report["items"][0]
        self.assertEqual(item["source_ids"], [11, 12])
        self.assertFalse(item["human_verified"])
        self.assertIn("2023/24", item["research_sentence"])
        self.assertNotIn("<", item["research_sentence"])

    def test_difference_between_lists_is_not_falsity_or_voiceover_permission(self):
        def change(data):
            data["facts"][0]["value"]["corroboration"] = "league_only"
            data["facts"][0]["evidence"].pop()
        report = self.report(change)
        self.assertEqual(report["counts"]["listing_difference"], 1)
        self.assertEqual(report["items"][0]["reason"], "source_lists_not_aligned")
        self.assertIsNone(report["items"][0]["research_sentence"])
        self.assertFalse(report["approved_for_voiceover"])

    def test_missing_second_profile_is_not_dubbed_source_disagreement(self):
        def change(data):
            data["facts"][0]["value"]["corroboration"] = "league_only"
            data["facts"][0]["evidence"].pop()
            data["sources"].pop()
        report = self.report(change)
        self.assertEqual(report["counts"]["listing_difference"], 0)
        self.assertEqual(report["counts"]["single_source"], 1)

    def test_matching_label_without_matching_provenance_is_not_accepted(self):
        for mutation in (
            lambda d: d["facts"][0]["evidence"].pop(),
            lambda d: d["sources"][1].update({"access_state": "restricted"}),
            lambda d: d["sources"][1].update({"external_id": "auto-p856-sites:" + QID}),
            lambda d: d["sources"][1].update({"external_id": "auto-honours-club:Q111"}),
            lambda d: d["sources"][1].update({"url": "https://www.bundesliga.at/teams"}),
            lambda d: d["facts"][0]["evidence"][1].update({
                "locator": "National success · 2024/25 · domestic_cup",
            }),
            lambda d: d["facts"][0]["evidence"][1].update({
                "role": "context_only",
            }),
        ):
            with self.subTest(mutation=mutation):
                report = self.report(mutation)
                self.assertEqual(report["counts"]["matching_records"], 0)

    def test_malicious_urls_do_not_yield_two_source_confirmation(self):
        for url in (
            "http://sksturm.at/en/c/steckbrief",
            "https://127.0.0.1/en/c/steckbrief",
            "https://sksturm.at:9999/path",
            "https://user:password@sksturm.at/path",
            "https://sksturm.at/?next=evil",
            "https://sksturm.at/#fragment",
            "https://sksturm.at:invalid/path",
            "https://evil domain.com/path",
        ):
            with self.subTest(url=url):
                report = self.report(
                    lambda d: d["sources"][1].update({"url": url})
                )
                self.assertEqual(report["counts"]["matching_records"], 0)

    def test_contradictions_or_rejections_take_precedence(self):
        report = self.report(lambda d: d["facts"][0]["evidence"][0].update({
            "role": "contradicts",
        }))
        self.assertEqual(report["counts"]["conflict"], 1)
        report = self.report(lambda d: d["facts"][0].update({
            "verification_state": "rejected",
        }))
        self.assertEqual(report["counts"]["excluded"], 1)

    def test_single_source_and_non_official_structured_facts_do_not_auto_pass(self):
        report = self.report(lambda d: d["facts"][0]["value"].update({
            "corroboration": "club_not_checked",
        }))
        self.assertEqual(report["counts"]["single_source"], 1)
        self.assertIsNone(report["items"][0]["research_sentence"])
        report = self.report(lambda d: d["facts"].append({
            "id": 22, "predicate": "founded_year", "value": 1909,
            "verification_state": "unverified", "evidence": [],
        }))
        self.assertEqual(report["counts"]["not_evaluated"], 1)
        self.assertEqual(report["counts"]["matching_records"], 1)

    def test_malformed_or_future_claims_are_not_machine_matched(self):
        for season, category in (
            ("2030/31", "domestic_cup"),
            ("2023/25", "domestic_cup"),
            ("2023-24", "domestic_cup"),
            ("2023/24", ["domestic_cup"]),
            ("2023/24", "friendly_cup"),
        ):
            with self.subTest(season=season, category=category):
                report = self.report(lambda d: d["facts"][0]["value"].update({
                    "season": season, "category": category,
                }))
                self.assertEqual(report["counts"]["matching_records"], 0)

    def test_bad_evidence_types_do_not_crash(self):
        for evidence in (None, "invalid", {}, [None, "invalid"]):
            with self.subTest(evidence=evidence):
                report = self.report(
                    lambda d: d["facts"][0].update({"evidence": evidence})
                )
                self.assertEqual(report["counts"]["matching_records"], 0)

    def test_limited_input_and_no_dossier_are_safe(self):
        with self.assertRaises(ValueError):
            assess_research_snapshot(None)
        data = example()
        data["facts"] = data["facts"] * 300
        result = assess_research_snapshot(data)
        self.assertEqual(result["total_facts_evaluated"], 250)
        self.assertEqual(result["additional_facts_not_evaluated"], 50)


class FilmMachineAssessmentBrowserTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="film-assess-owner@example.org", password="test-password-12345",
        )
        self.foreign = User.objects.create_user(
            email="film-assess-foreign@example.org", password="test-password-12345",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(
            country=country, name="Austrian Bundesliga",
        )
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.user, club=club, club_name="Sturm Graz",
            country_code="AT", league_name=league.name,
            title="The Story of Sturm Graz", kind=ProductionJob.Kind.FILM,
            status=ProductionJob.Status.QUEUED,
        )
        dossier = FactDossier.objects.create(job=self.job, version=1)
        for source in example()["sources"]:
            SourceReference.objects.create(
                id=source["id"], dossier=dossier,
                source_kind=source["source_kind"], url=source["url"],
                external_id=source["external_id"],
                retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
                access_state=source["access_state"], title="Official list",
            )
        fact = Fact.objects.create(
            dossier=dossier, predicate="club_honour_candidate",
            value=example()["facts"][0]["value"],
            assertion_text="The club won the domestic cup in 2023/24.",
        )
        for row in example()["facts"][0]["evidence"]:
            Evidence.objects.create(
                fact=fact, source_id=row["source_id"],
                role=row["role"], locator=row["locator"],
                summary="A season listing from an automatically fetched official page.",
            )
        self.client.force_login(self.user)

    def test_film_status_auto_shows_machine_agreement_without_reviews(self):
        page = self.client.get(
            reverse("film-status-page", kwargs={"job_id": self.job.pk}),
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Automatische Belegbewertung")
        self.assertContains(page, "übereinstimmende Titelangaben")
        self.assertContains(page, "2023/24")
        self.assertContains(page, "Keine automatisch verifizierten Fakten")
        result = self.client.get(
            reverse("production:film-status", kwargs={"job_id": self.job.pk}),
        ).json()["job"]["machine_source_assessment"]
        self.assertEqual(result["counts"]["matching_records"], 1)
        self.assertFalse(result["approved_for_voiceover"])
        self.assertFalse(FactReview.objects.exists())
        self.assertEqual(
            Fact.objects.get(dossier__job=self.job).verification_state,
            Fact.Verification.UNVERIFIED,
        )

    def test_other_owner_cannot_read_assessment(self):
        self.client.force_login(self.foreign)
        page = self.client.get(
            reverse("film-status-page", kwargs={"job_id": self.job.pk}),
        )
        self.assertEqual(page.status_code, 404)
        response = self.client.get(
            reverse("production:film-status", kwargs={"job_id": self.job.pk}),
        )
        self.assertEqual(response.status_code, 404)
