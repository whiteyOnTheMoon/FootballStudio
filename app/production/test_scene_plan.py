"""FS-016c offline storyboard planning regressions; never fetch media."""
from copy import deepcopy
from unittest.mock import patch

from django.test import SimpleTestCase

from .scene_plan import ScenePlanError, build_scene_plan
from .script_draft import build_script_draft
from .test_script_draft import reviewed_snapshot


def fixture_draft():
    return build_script_draft(
        reviewed_snapshot(), club_name="Example FC",
        selected_title="Example FC: A Sourced History",
    )


class OfflineScenePlanTests(SimpleTestCase):
    def test_opening_fact_closing_have_contiguous_timing_and_sources(self):
        plan = build_scene_plan(fixture_draft())
        scenes = plan["scenes"]
        self.assertEqual(len(scenes), 3)
        self.assertEqual(
            [(item["scene_number"], item["section"]) for item in scenes],
            [(1, "opening"), (2, "main"), (3, "closing")],
        )
        self.assertEqual(scenes[0]["start_ms_estimate"], 0)
        self.assertEqual(scenes[-1]["end_ms_estimate"],
                         plan["estimated_total_ms"])
        for previous, current in zip(scenes, scenes[1:]):
            self.assertEqual(previous["end_ms_estimate"],
                             current["start_ms_estimate"])
        for scene in scenes:
            self.assertGreater(scene["duration_ms_estimate"], 0)
            self.assertEqual(scene["visual"]["kind"],
                             "original_text_card_placeholder")
            self.assertFalse(scene["visual"]["rights_cleared"])
            self.assertFalse(scene["visual"]["external_media_selected"])
        self.assertIsNone(scenes[0]["fact_id"])
        self.assertEqual(scenes[0]["evidence_refs"], [])
        self.assertEqual(scenes[1]["fact_id"], 21)
        self.assertEqual(scenes[1]["segment_id"], "fact-21")
        self.assertEqual(scenes[1]["evidence_refs"], [{
            "source_id": 11, "url": "https://club.example.org/history",
        }])
        self.assertIsNone(scenes[2]["fact_id"])
        self.assertTrue(plan["editorial_review_required"])
        self.assertFalse(plan["ready_for_tts"])
        self.assertFalse(plan["ready_for_render"])
        self.assertEqual(plan, build_scene_plan(fixture_draft()))
        self.assertEqual(len(plan["plan_fingerprint_sha256"]), 64)

    def test_speed_changes_timing_but_not_narration_and_evidence(self):
        draft = fixture_draft()
        slow = build_scene_plan(draft, words_per_minute=110)
        fast = build_scene_plan(draft, words_per_minute=180)
        self.assertGreater(slow["estimated_total_ms"],
                           fast["estimated_total_ms"])
        self.assertEqual(
            [x["evidence_refs"] for x in slow["scenes"]],
            [x["evidence_refs"] for x in fast["scenes"]],
        )
        self.assertEqual(
            [x["narration"] for x in slow["scenes"]],
            [x["narration"] for x in fast["scenes"]],
        )
        self.assertNotEqual(slow["plan_fingerprint_sha256"],
                            fast["plan_fingerprint_sha256"])

    def test_length_failures_still_return_unapproved_planning_only(self):
        plan = build_scene_plan(fixture_draft())
        self.assertEqual(plan["script_length_status"], "too_short")
        self.assertFalse(plan["ready_for_tts"])
        self.assertFalse(plan["ready_for_render"])

    def test_stale_and_malformed_script_fails_closed(self):
        original = fixture_draft()
        for edit in (
            lambda d: d.update(voiceover_text="Unreviewed text"),
            lambda d: d["sections"][1]["segments"][0].update(
                narration="The club also won an imaginary competition."
            ),
            lambda d: d["sections"][1]["segments"][0]["evidence_refs"][0].update(
                url="https://unreviewed.example.org"
            ),
            lambda d: d.update(input_fingerprint_sha256="0" * 64),
            lambda d: d.update(language="de"),
            lambda d: d.update(ready_for_tts=True),
        ):
            draft = deepcopy(original)
            edit(draft)
            with self.assertRaises(ScenePlanError):
                build_scene_plan(draft)
        with self.assertRaisesMessage(ScenePlanError, "invalid_speaking_rate"):
            build_scene_plan(original, words_per_minute=99)

    def test_bad_segment_ids_are_rejected_even_with_valid_fingerprint(self):
        # The fingerprint is a consistency check, not a source of authority:
        # this test rebuilds it to emulate internal structured edits.
        from hashlib import sha256
        import json
        for segment_id in ("../../other", "fact-999", ""):
            draft = fixture_draft()
            draft["sections"][1]["segments"][0]["id"] = segment_id
            raw = {key: value for key, value in draft.items()
                   if key != "input_fingerprint_sha256"}
            draft["input_fingerprint_sha256"] = sha256(
                json.dumps(raw, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            with self.assertRaisesMessage(ScenePlanError, "invalid_segment_id"):
                build_scene_plan(draft)

    @patch("urllib.request.urlopen")
    @patch("socket.getaddrinfo")
    def test_no_network_or_media_fetch(self, dns, http):
        build_scene_plan(fixture_draft())
        dns.assert_not_called()
        http.assert_not_called()
