"""FS-016b.1: offline length-budget and pre-TTS gate regressions."""
from copy import deepcopy
from unittest.mock import patch

from django.test import SimpleTestCase

from .script_draft import build_script_draft
from .script_length import (
    ScriptLengthError, plan_script_draft_length, plan_spoken_text,
    require_script_length_before_tts,
)
from .test_script_draft import reviewed_snapshot


class LengthPlannerTests(SimpleTestCase):
    def test_8_to_10_minute_boundary_is_exact_at_145_wpm(self):
        for count, status, adjustment, action in [
            (1159, "too_short", 1, "add_source_reviewed_content"),
            (1160, "within_target", 0, "editorial_review"),
            (1305, "within_target", 0, "editorial_review"),
            (1450, "within_target", 0, "editorial_review"),
            (1451, "too_long", 1, "edit_down_preserving_evidence"),
        ]:
            with self.subTest(word_count=count):
                report = plan_spoken_text("story " * count)
                self.assertEqual(report["word_count"], count)
                self.assertEqual(report["minimum_words"], 1160)
                self.assertEqual(report["target_words"], 1305)
                self.assertEqual(report["maximum_words"], 1450)
                self.assertEqual(report["status"], status)
                self.assertEqual(report["required_word_adjustment"], adjustment)
                self.assertEqual(report["recommended_action"], action)
                self.assertEqual(report["length_within_target"],
                                 status == "within_target")
                self.assertFalse(report["ready_for_tts"])

    def test_configurable_speaking_speed_adjusts_all_thresholds(self):
        slow = plan_spoken_text("story " * 1200, words_per_minute=120)
        fast = plan_spoken_text("story " * 1200, words_per_minute=180)
        self.assertEqual(
            (slow["minimum_words"], slow["maximum_words"]), (960, 1200)
        )
        self.assertEqual(
            (fast["minimum_words"], fast["maximum_words"]), (1440, 1800)
        )
        self.assertEqual(slow["estimated_seconds"], 600.0)
        self.assertEqual(fast["estimated_seconds"], 400.0)
        self.assertEqual(slow["status"], "within_target")
        self.assertEqual(fast["status"], "too_short")

    def test_reject_invalid_rate_including_bool_float_and_strings(self):
        for rate in (0, -1, 99, 201, True, False, 145.0, "145", None):
            with self.subTest(rate=rate), self.assertRaisesMessage(
                ScriptLengthError, "invalid_speaking_rate"
            ):
                plan_spoken_text("A few safe words.", words_per_minute=rate)
        self.assertEqual(
            plan_spoken_text("word", words_per_minute=100)["minimum_words"], 800
        )
        self.assertEqual(
            plan_spoken_text("word", words_per_minute=200)["maximum_words"], 2000
        )

    def test_unicode_club_names_seasons_and_contractions_are_counted(self):
        report = plan_spoken_text(
            "Manchester United's 2025/26 season, Atlético-Madrid."
        )
        self.assertEqual(report["word_count"], 6)

    def test_invalid_text_fails_closed(self):
        for value in (
            "", " ", "?", " \n  ", "hi\tthere",
            "Hello\rWorld", "<script>oops</script>", 1,
            "word " * 25000,
        ):
            with self.subTest(value=str(value)[:20]), self.assertRaisesMessage(
                ScriptLengthError, "invalid_voiceover"
            ):
                plan_spoken_text(value)

    @patch("urllib.request.urlopen")
    @patch("socket.getaddrinfo")
    def test_planner_does_not_perform_dns_http_or_paid_calls(self, dns, http):
        text = "A reviewed club story with no external calls."
        self.assertEqual(plan_spoken_text(text), plan_spoken_text(text))
        dns.assert_not_called()
        http.assert_not_called()


class ScriptDraftLengthTests(SimpleTestCase):
    def make_draft(self):
        return build_script_draft(
            reviewed_snapshot(), club_name="Example FC",
            selected_title="A Club Documentary",
        )

    def test_real_script_draft_is_analyzed_but_not_authorized_for_tts(self):
        draft = self.make_draft()
        report = plan_script_draft_length(draft)
        self.assertEqual(report["job_id"], draft["job_id"])
        self.assertEqual(report["dossier_version"], draft["dossier_version"])
        self.assertEqual(
            report["script_fingerprint_sha256"],
            draft["input_fingerprint_sha256"],
        )
        self.assertEqual(
            report["word_count"], sum(report["section_word_counts"].values())
        )
        self.assertGreater(report["section_word_counts"]["main"], 0)
        self.assertEqual(report["status"], "too_short")
        self.assertGreater(report["required_word_adjustment"], 1000)
        self.assertTrue(report["editorial_review_required"])
        self.assertFalse(report["ready_for_tts"])
        self.assertEqual(report, plan_script_draft_length(draft))

    def test_short_draft_is_explicitly_blocked_before_tts(self):
        with self.assertRaisesMessage(ScriptLengthError, "too_short"):
            require_script_length_before_tts(self.make_draft())

    def test_script_body_or_citation_edits_invalidate_existing_fingerprint(self):
        for edit in (
            lambda d: d.update(voiceover_text="Long fake input"),
            lambda d: d["sections"][1]["segments"][0].update(
                narration="An unreviewed new historical claim."
            ),
            lambda d: d["sections"][1]["segments"][0]["evidence_refs"][0].update(
                url="https://unreviewed.example.org"
            ),
            lambda d: d.update(selected_title_for_review="A different title"),
        ):
            draft = self.make_draft()
            edit(draft)
            with self.assertRaises(ScriptLengthError):
                plan_script_draft_length(draft)

    def test_malformed_drafts_never_pass(self):
        source = self.make_draft()
        for change in (
            {"schema": "unknown"},
            {"language": "de"},
            {"editorial_review_required": False},
            {"ready_for_tts": True},
            {"job_id": True},
            {"dossier_version": 0},
            {"sections": []},
            {"sections": ["not a section"]},
            {"input_fingerprint_sha256": "x" * 64},
        ):
            draft = deepcopy(source)
            draft.update(change)
            with self.subTest(change=change), self.assertRaises(
                ScriptLengthError
            ):
                plan_script_draft_length(draft)

    @patch("urllib.request.urlopen")
    @patch("socket.getaddrinfo")
    def test_integration_stays_offline(self, dns, http):
        plan_script_draft_length(self.make_draft())
        dns.assert_not_called()
        http.assert_not_called()
