"""Deterministic, offline narration length planning for M2 (FS-016b).

Word counts estimate speaking time, not actual synthesized audio duration.
Actual TTS runtime must be measured separately before final rendering.
"""
from dataclasses import dataclass
import re


_WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True)
class NarrationLength:
    words: int
    minimum_words: int
    target_words: int
    maximum_words: int
    estimated_seconds: int
    status: str
    correction: str


def plan_narration(text: str, *, words_per_minute: int = 140,
                   minimum_minutes: int = 8, target_minutes: int = 9,
                   maximum_minutes: int = 10) -> NarrationLength:
    """Assess English narration against configurable runtime boundaries.

    Raises ValueError for invalid settings; contains no API or database calls.
    """
    if not isinstance(text, str):
        raise TypeError("Narration text must be a string")
    settings = (words_per_minute, minimum_minutes, target_minutes, maximum_minutes)
    if any(type(value) is not int or value <= 0 for value in settings):
        raise ValueError("Speaking rate and durations must be positive integers")
    if words_per_minute > 300 or not (
        minimum_minutes <= target_minutes <= maximum_minutes
    ):
        raise ValueError("Invalid speaking rate or duration range")

    words = len(_WORD.findall(text))
    low = words_per_minute * minimum_minutes
    target = words_per_minute * target_minutes
    high = words_per_minute * maximum_minutes
    seconds = round(words * 60 / words_per_minute)
    if words < low:
        status = "too_short"
        correction = f"Add at least {low - words} additional spoken words before TTS."
    elif words > high:
        status = "too_long"
        correction = f"Remove at least {words - high} spoken words before TTS."
    else:
        status = "within_range"
        correction = "Word-count estimate accepted; verify actual TTS duration."
    return NarrationLength(words, low, target, high, seconds, status, correction)
