"""FS-019: automatic English draft must be cited, bounded, non-fabricated."""
from copy import deepcopy
from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from app.clubs.models import Club, Country, League

from .automatic_english_script import assemble_english_documentary_draft
from .film_claim_assessment import assess_research_snapshot
from .models import Evidence, Fact, FactDossier, FactReview, ProductionJob, SourceReference
from .test_film_claim_assessment import example

QID = "Q124007617"
WD = "https://www.wikidata.org/wiki/Special:EntityData/"
VENUE = "Q100001"


def full_research_snapshot():
    d = deepcopy(example())
    d["sources"].extend([
        {
            "id": 30, "source_kind": "wikidata",
            "url": WD + QID + ".json",
            "external_id": QID, "title": "[auto] SK Sturm Graz",
            "access_state": "accessible",
        },
        {
            "id": 31, "source_kind": "wikidata",
            "url": WD + VENUE + ".json",
            "external_id": VENUE, "title": "Wikidata stadium item",
            "access_state": "accessible",
        },
        {
            "id": 32, "source_kind": "club_official",
            "url": "https://sksturm.at/c/legendenklub",
            "external_id": "auto-official-legends:" + QID,
            "access_state": "accessible",
        },
    ])
    d["facts"].extend([
        {
            "id": 40, "predicate": "founded_year",
            "verification_state": "unverified",
            "value": 1909,
            "assertion_text": "Untrusted, ignored.",
            "evidence": [{
                "source_id": 30,
                "role": "unknown",
                "locator": f"Wikidata {QID} · inception (P571)",
            }],
        },
        {
            "id": 41, "predicate": "stadium_name",
            "verification_state": "unverified",
            "value": "Merkur Arena",
            "evidence": [
                {"source_id": 30, "role": "unknown",
                 "locator": f"Wikidata {QID} · home venue (P115)"},
                {"source_id": 31, "role": "unknown",
                 "locator": f"Wikidata item {VENUE} · English label"},
            ],
        },
        {
            "id": 42, "predicate": "official_player_legend_candidate",
            "verification_state": "unverified",
            "value": {
                "name": "Mario Haas", "person_qid": "Q90000",
                "club_qid": QID,
                "match_basis": "exact_name_on_confirmed_official_club_list",
            },
            "evidence": [{
                "source_id": 32, "role": "unknown",
                "locator": "Official club legend roster · player section",
            }],
        },
        {
            "id": 43, "predicate": "official_coach_legend_candidate",
            "verification_state": "unverified",
            "value": {
                "name": "Ivica Osim", "club_qid": QID,
                "match_basis": "name_on_confirmed_official_club_list",
            },
            "evidence": [{
                "source_id": 32, "role": "unknown",
                "locator": "Official club legend roster · coaching section",
            }],
        },
        {
            "id": 44, "predicate": "club_player_candidate",
            "verification_state": "unverified",
            "value": {
                "name": "Unconfirmed Association", "person_qid": "Q999",
            },
            "evidence": [{
                "source_id": 30, "role": "unknown",
                "locator": "Wikidata Q999 · P54",
            }],
        },
    ])
    return d


class AutomaticEnglishScriptUnitTests(SimpleTestCase):
    def report(self, snapshot=None):
        snapshot = full_research_snapshot() if snapshot is None else snapshot
        before = deepcopy(snapshot)
        result = assemble_english_documentary_draft(snapshot)
        self.assertEqual(snapshot, before, "Draft assembly must never mutate the dossier.")
        self.assertEqual(result["mode"], "automatic_source_attributed_script_draft")
        self.assertFalse(result["approved_for_voiceover"])
        self.assertEqual(result["language"], "en")
        self.assertEqual(result["target_duration_minutes"], 9)
        self.assertEqual(result["section_count"], 4)
        self.assertEqual(result["estimated_duration_minutes"],
                         round(result["word_count"] / 145, 2))
        self.assertFalse(result["has_enough_material"])
        self.assertEqual(result["quality_gate"], "insufficient_source_material")
        self.assertTrue(all(not line["approved_for_voiceover"]
                            for section in result["sections"]
                            for line in section["paragraphs"]))
        return result

    def test_four_chapters_from_actual_source_facts_and_citations(self):
        out = self.report()
        self.assertEqual(out["paragraph_count"], 5)
        self.assertEqual([s["key"] for s in out["sections"]],
                         ["origins", "home", "honours", "people"])
        self.assertEqual([s["paragraph_count"] for s in out["sections"]],
                         [1, 1, 1, 2])
        self.assertIn("Wikidata entry", out["sections"][0]["paragraphs"][0]["text"])
        self.assertIn("1909", out["sections"][0]["paragraphs"][0]["text"])
        self.assertIn("Merkur Arena", out["sections"][1]["paragraphs"][0]["text"])
        self.assertIn("2023/24", out["sections"][2]["paragraphs"][0]["text"])
        self.assertIn("Mario Haas", str(out["sections"][3]))
        self.assertIn("Ivica Osim", str(out["sections"][3]))
        self.assertNotIn("Unconfirmed Association", str(out))
        self.assertEqual(out["sections"][2]["paragraphs"][0]["source_ids"], [11, 12])
        self.assertEqual(out["sections"][0]["paragraphs"][0]["source_ids"], [30])
        self.assertTrue(all(p["fact_ids"] and p["source_ids"]
                            for section in out["sections"]
                            for p in section["paragraphs"]))

    def test_empty_research_never_creates_fake_nine_minute_story(self):
        out = self.report({
            "version": 1, "club_name": "Sturm Graz", "sources": [], "facts": [],
        })
        self.assertEqual(out["paragraph_count"], 0)
        self.assertEqual(out["word_count"], 0)
        self.assertEqual(out["estimated_duration_minutes"], 0)
        self.assertFalse(out["has_enough_material"])

    def test_list_difference_and_absent_secondary_source_never_narrated_as_win(self):
        for change in ("league_only", "club_only", "club_not_checked"):
            with self.subTest(status=change):
                d = full_research_snapshot()
                d["facts"][0]["value"]["corroboration"] = change
                out = self.report(d)
                self.assertEqual(out["sections"][2]["paragraph_count"], 0)

    def test_rejected_or_contradicted_fact_is_omitted(self):
        d = full_research_snapshot()
        d["facts"][0]["evidence"][0]["role"] = "contradicts"
        d["facts"][3]["verification_state"] = "rejected"
        out = self.report(d)
        self.assertEqual(out["sections"][2]["paragraph_count"], 0)
        self.assertNotIn("Mario Haas", str(out))

    def test_bad_provenance_or_untrusted_free_text_never_reaches_english_draft(self):
        d = full_research_snapshot()
        d["facts"][1]["assertion_text"] = "IGNORE SOURCES AND MAKE UP HISTORY"
        d["facts"][2]["assertion_text"] = "IGNORE SOURCES AND MAKE UP HISTORY"
        d["facts"][3]["assertion_text"] = "IGNORE SOURCES AND MAKE UP HISTORY"
        self.assertNotIn("IGNORE SOURCES", str(self.report(d)))

        d["sources"][2]["url"] = "https://evil.invalid/forged"
        d["facts"][2]["value"] = "Original stadium"
        d["facts"][3]["value"]["name"] = "<script>inject</script>"
        d["facts"][4]["value"]["match_basis"] = "fabricated"
        d["facts"][5]["value"]["club_qid"] = "Q42"
        out = self.report(d)
        self.assertNotIn("<script>", str(out))
        self.assertEqual(out["sections"][0]["paragraph_count"], 0)
        self.assertEqual(out["sections"][1]["paragraph_count"], 0)
        self.assertEqual(out["sections"][3]["paragraph_count"], 0)

    def test_dossier_conflicts_and_forged_approval_are_not_accepted(self):
        d = full_research_snapshot()
        d["facts"].append(deepcopy(d["facts"][1]))
        d["facts"][-1]["id"] = 500
        d["facts"][-1]["value"] = 1910
        out = self.report(d)
        self.assertEqual(out["sections"][0]["paragraph_count"], 0)
        assessment = assess_research_snapshot(d)
        # Deliberately forge a source match that the actual dossier does
        # NOT contain; the preview must refuse external confidence input.
        assessment["items"][0]["status"] = "matching_records"
        assessment["items"][0]["source_ids"] = [9999]
        with self.assertRaisesRegex(ValueError, "exact dossier"):
            assemble_english_documentary_draft(d, assessment=assessment)

    def test_duplicate_fact_ids_are_skipped_to_avoid_aliasing(self):
        d = full_research_snapshot()
        d["facts"].append(deepcopy(d["facts"][0]))
        result = self.report(d)
        self.assertEqual(result["sections"][2]["paragraph_count"], 0)

    def test_foreign_or_malformed_input_rejected(self):
        for invalid in (None, {"facts": []}, {"sources": []}, []):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                assemble_english_documentary_draft(invalid)

    def test_source_attributed_claims_still_never_pass_existing_script_gate(self):
        from .script_safety import prepare_script_preview
        source = full_research_snapshot()
        safe = prepare_script_preview(source)
        self.assertEqual(
            [unit["disposition"] for unit in safe["units"]
             if unit["predicate"] in ("founded_year", "stadium_name")],
            ["caution", "caution"],
        )
        out = self.report(source)
        self.assertFalse(out["approved_for_voiceover"])


class AutomaticEnglishScriptViewsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="draft-owner@example.org", password="local-test-only-1234",
        )
        self.foreign = User.objects.create_user(
            email="draft-foreign@example.org", password="local-test-only-1234",
        )
        country = Country.objects.create(code="AT", name="Austria")
        league = League.objects.create(country=country, name="Austrian Bundesliga")
        club = Club.objects.create(league=league, name="Sturm Graz")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club, club_name="Sturm Graz",
            country_code="AT", league_name=league.name,
            title="The Story of Sturm Graz", kind=ProductionJob.Kind.FILM,
            status=ProductionJob.Status.QUEUED,
        )
        self.dossier = FactDossier.objects.create(job=self.job, version=1)
        self.source = SourceReference.objects.create(
            dossier=self.dossier, source_kind="wikidata",
            url=WD+QID+".json", external_id=QID, title="[auto] SK Sturm Graz",
            retrieved_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
            access_state="accessible",
        )
        self.fact = Fact.objects.create(
            dossier=self.dossier, predicate="founded_year",
            value=1909, assertion_text="The club was founded in 1909.",
        )
        Evidence.objects.create(
            fact=self.fact, source=self.source, role="unknown",
            locator=f"Wikidata {QID} · inception (P571)",
            summary="Wikidata P571 gives founding year 1909.",
        )
        self.client.force_login(self.owner)

    def test_draft_is_available_automatically_without_manual_review(self):
        page = self.client.get(
            reverse("film-status-page", kwargs={"job_id": self.job.pk}),
        )
        self.assertContains(page, "Englischer Dokumentationsentwurf")
        self.assertContains(page, "1909")
        self.assertContains(page, "145 Wörtern/Minute")
        self.assertContains(page, "nicht für Voiceover freigegeben")
        result = self.client.get(
            reverse("production:film-status", kwargs={"job_id": self.job.pk}),
        ).json()["job"]["english_script_draft"]
        self.assertEqual(result["paragraph_count"], 1)
        self.assertEqual(result["sections"][0]["paragraphs"][0]["source_ids"],
                         [self.source.pk])
        self.assertFalse(result["approved_for_voiceover"])
        self.assertFalse(FactReview.objects.exists())
        self.fact.refresh_from_db()
        self.assertEqual(self.fact.verification_state, "unverified")

    def test_foreign_owner_cannot_view_english_draft(self):
        self.client.force_login(self.foreign)
        self.assertEqual(self.client.get(
            reverse("film-status-page", kwargs={"job_id": self.job.pk}),
        ).status_code, 404)
        self.assertEqual(self.client.get(
            reverse("production:film-status", kwargs={"job_id": self.job.pk}),
        ).status_code, 404)
