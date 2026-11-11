"""M2 narrator runtime estimator boundary and validation tests."""
from django.test import SimpleTestCase

from app.production.narration_length import plan_narration


class NarrationLengthTests(SimpleTestCase):
    def test_empty_script_requires_words(self):
        result = plan_narration("")
        self.assertEqual(result.words, 0)
        self.assertEqual((result.minimum_words, result.target_words, result.maximum_words),
                         (1120, 1260, 1400))
        self.assertEqual(result.status, "too_short")
        self.assertIn("1120", result.correction)

    def test_exact_minimum_and_maximum_are_accepted(self):
        for count in (1120, 1400):
            with self.subTest(count=count):
                result = plan_narration("word " * count)
                self.assertEqual(result.words, count)
                self.assertEqual(result.status, "within_range")

    def test_one_word_past_maximum_requests_reduction(self):
        result = plan_narration("word " * 1401)
        self.assertEqual(result.status, "too_long")
        self.assertIn("1 spoken words", result.correction)

    def test_configurable_rate_changes_target_and_estimate(self):
        result = plan_narration("word " * 900, words_per_minute=100)
        self.assertEqual(result.target_words, 900)
        self.assertEqual(result.estimated_seconds, 540)
        self.assertEqual(result.status, "within_range")

    def test_punctuation_and_apostrophes_are_not_separate_words(self):
        result = plan_narration("It's a team's 100-year history.\nAnother chapter!")
        self.assertEqual(result.words, 6)

    def test_invalid_settings_fail_closed(self):
        for rate in (0, -1, 301, 140.5, True):
            with self.subTest(rate=rate):
                with self.assertRaises(ValueError):
                    plan_narration("example", words_per_minute=rate)
        with self.assertRaises(ValueError):
            plan_narration("example", minimum_minutes=10, target_minutes=9)
        with self.assertRaises(TypeError):
            plan_narration(None)
