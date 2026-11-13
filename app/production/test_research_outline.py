"""Research beat sheet keeps every unverified source candidate out of narration."""
from django.test import SimpleTestCase

from .research_outline import build_documentary_research_outline


def row(pk, predicate, value, *, reviewed=False, sources=(1,)):
    return {
        "id": pk, "predicate": predicate, "value": value,
        "verification_state": "verified" if reviewed else "unverified",
        "review": {"decision": "verified"} if reviewed else None,
        "evidence": [{"source_id": sid} for sid in sources],
    }


class DocumentaryResearchOutlineTests(SimpleTestCase):
    def snapshot(self):
        return {
            "sources": [
                {"id": 1, "url": "https://www.wikidata.org/"},
                {"id": 2, "url": "https://sksturm.at/"},
                {"id": 3, "url": "https://www.bundesliga.at/"},
            ],
            "facts": [
                row(1, "founded_year", 1909, sources=(1,)),
                row(2, "stadium_name", "Merkur Arena", sources=(1,)),
                row(3, "club_honour_candidate", {
                    "season": "2023/24", "category": "domestic_cup",
                    "corroboration": "league_only",
                }, sources=(2, 3)),
                row(4, "official_player_legend_candidate", {
                    "name": "Mario Haas",
                }, sources=(2,)),
                row(5, "official_coach_legend_candidate", {
                    "name": "Ivica Osim",
                }, sources=(2,)),
                row(6, "club_player_candidate", {
                    "name": "Other Player",
                }, sources=(1,)),
            ],
        }

    def test_produces_four_research_only_chapters_for_nine_minute_target(self):
        outline = build_documentary_research_outline(self.snapshot())
        self.assertEqual(outline["mode"], "research_outline_only")
        self.assertEqual(outline["target_duration_minutes"], 9)
        self.assertFalse(outline["ready_for_voiceover"])
        self.assertEqual(outline["total_candidate_count"], 5)
        self.assertEqual(outline["reviewed_count"], 0)
        self.assertEqual(
            [b["key"] for b in outline["sections"]],
            ["origins", "home", "trophies", "people"],
        )
        self.assertEqual(
            [b["time_window"] for b in outline["sections"]],
            ["0:00–1:00", "1:00–2:00", "2:00–6:30", "6:30–9:00"],
        )
        self.assertIn(
            "2023/24: Domestic cup — League listing; club profile does not list it",
            outline["sections"][2]["items"][0]["label"],
        )
        self.assertEqual(outline["sections"][2]["items"][0]["source_ids"], [2, 3])
        self.assertFalse(any(
            "Other Player" in i["label"]
            for section in outline["sections"]
            for i in section["items"]
        ))

    def test_no_reviewer_means_no_verified_label(self):
        data = self.snapshot()
        data["facts"][0]["verification_state"] = "verified"
        data["facts"][0]["review"] = None
        result = build_documentary_research_outline(data)
        self.assertEqual(result["sections"][0]["items"][0]["status"], "unverified")
        self.assertEqual(result["reviewed_count"], 0)
        data["facts"][0]["review"] = {"decision": "verified"}
        result = build_documentary_research_outline(data)
        self.assertEqual(result["sections"][0]["items"][0]["status"], "reviewed")
        self.assertFalse(result["ready_for_voiceover"])

    def test_missing_evidence_source_reference_does_not_become_citation(self):
        data = self.snapshot()
        data["facts"][0]["evidence"].append({"source_id": 9999})
        data["facts"][0]["evidence"].append({"source_id": "1"})
        result = build_documentary_research_outline(data)
        self.assertEqual(result["sections"][0]["items"][0]["source_ids"], [1])

    def test_forged_or_malformed_honours_not_treated_as_timelines(self):
        data = self.snapshot()
        data["facts"].append(row(10, "club_honour_candidate", {
            "season": "2024/25", "category": "unlisted_trophy",
            "corroboration": "both",
        }))
        data["facts"].append(row(11, "club_honour_candidate", {
            "season": "2024-25", "category": "league_champion",
            "corroboration": "both",
        }))
        result = build_documentary_research_outline(data)
        self.assertEqual(result["sections"][2]["candidate_count"], 1)

    def test_bounded_beat_candidates_and_full_count(self):
        data = self.snapshot()
        for i in range(15):
            data["facts"].append(row(100 + i, "club_honour_candidate", {
                "season": f"20{i:02d}/" + f"{(i + 1) % 100:02d}",
                "category": "league_champion",
                "corroboration": "both",
            }))
        result = build_documentary_research_outline(data)
        beat = result["sections"][2]
        self.assertEqual(beat["candidate_count"], 16)
        self.assertEqual(len(beat["items"]), 10)
        self.assertEqual(beat["additional_count"], 6)

    def test_invalid_or_empty_snapshot_safe(self):
        with self.assertRaisesMessage(ValueError, "Invalid research dossier"):
            build_documentary_research_outline(None)
        result = build_documentary_research_outline({
            "sources": [], "facts": [],
        })
        self.assertEqual(result["total_candidate_count"], 0)
        self.assertFalse(result["ready_for_voiceover"])
        self.assertEqual(len(result["sections"]), 4)
