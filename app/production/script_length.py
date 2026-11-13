"""FS-016b.1: deterministic, offline English voiceover length planning.

A word-count estimate is NOT audio timing. This module cannot initiate TTS,
change a job status, expand claims, contact an LLM or spend API budget.
"""
from hashlib import sha256
import json
import re

DEFAULT_WORDS_PER_MINUTE = 145
MIN_WORDS_PER_MINUTE = 100
MAX_WORDS_PER_MINUTE = 200
MIN_TARGET_MINUTES = 8
MAX_TARGET_MINUTES = 10
TARGET_MINUTES = 9

# English narration can contain non-ASCII club names and hyphenated names.
# Numbers (including years) count as spoken word-like tokens; seasons such
# as 2025/26 count as two. This is an estimate, not a pronunciation engine.
_WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class ScriptLengthError(ValueError):
    """Only stable codes; never echo private script text."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _valid_voiceover(value):
    return (
        type(value) is str
        and 1 <= len(value) <= 100_000
        and any(char.isalnum() for char in value)
        and all(char == "\n" or char.isprintable() for char in value)
        and "<" not in value and ">" not in value
    )


def plan_spoken_text(text, *, words_per_minute=DEFAULT_WORDS_PER_MINUTE):
    """Return a reproducible 8–10 minute word budget at a configured WPM.

    The upper/lower bounds use exact integer arithmetic so a fractional
    duration rounded for display cannot incorrectly pass the gate.
    """
    if (
        type(words_per_minute) is not int
        or not MIN_WORDS_PER_MINUTE <= words_per_minute <= MAX_WORDS_PER_MINUTE
    ):
        raise ScriptLengthError("invalid_speaking_rate")
    if not _valid_voiceover(text):
        raise ScriptLengthError("invalid_voiceover")

    words = len(_WORD.findall(text))
    if words == 0:
        raise ScriptLengthError("invalid_voiceover")
    minimum = words_per_minute * MIN_TARGET_MINUTES
    maximum = words_per_minute * MAX_TARGET_MINUTES
    if words < minimum:
        status = "too_short"
        action = "add_source_reviewed_content"
        difference = minimum - words
    elif words > maximum:
        status = "too_long"
        action = "edit_down_preserving_evidence"
        difference = words - maximum
    else:
        status = "within_target"
        action = "editorial_review"
        difference = 0

    return {
        "schema": "fs-016b-length-plan-v1",
        "language": "en",
        "words_per_minute": words_per_minute,
        "min_target_minutes": MIN_TARGET_MINUTES,
        "max_target_minutes": MAX_TARGET_MINUTES,
        "word_count": words,
        "minimum_words": minimum,
        "target_words": words_per_minute * TARGET_MINUTES,
        "maximum_words": maximum,
        "estimated_seconds": round(words * 60 / words_per_minute, 1),
        "status": status,
        "required_word_adjustment": difference,
        "recommended_action": action,
        "length_within_target": status == "within_target",
        # Word count alone can never approve content or dispatch paid TTS.
        "ready_for_tts": False,
    }


def plan_script_draft_length(draft, *, words_per_minute=DEFAULT_WORDS_PER_MINUTE):
    """Check an internally generated FS-016a draft, not arbitrary site text.

    The fingerprint checks consistency after editing/serialization, not
    cryptographic provenance or proof of reviewed facts. Only trusted code
    may originate the draft, using an owner-scoped dossier.
    """
    if not isinstance(draft, dict) or (
        draft.get("schema") != "fs-016a-offline-script-v1"
        or draft.get("language") != "en"
        or draft.get("mode") != "offline_reviewed_facts_only"
        or draft.get("editorial_review_required") is not True
        or draft.get("ready_for_tts") is not False
        or type(draft.get("job_id")) is not int or draft["job_id"] <= 0
        or type(draft.get("dossier_version")) is not int
        or draft["dossier_version"] <= 0
    ):
        raise ScriptLengthError("invalid_script_draft")

    sections = draft.get("sections")
    if (
        not isinstance(sections, list) or len(sections) != 3
        or any(not isinstance(section, dict) for section in sections)
        or [section.get("key") for section in sections]
        != ["opening", "main", "closing"]
    ):
        raise ScriptLengthError("invalid_script_draft")

    text_parts = []
    section_word_counts = {}
    for section in sections:
        segments = section.get("segments")
        if (
            not isinstance(segments, list)
            or not 1 <= len(segments) <= 2000
            or (section["key"] != "main" and len(segments) != 1)
        ):
            raise ScriptLengthError("invalid_script_draft")
        subtotal = 0
        for segment in segments:
            if not isinstance(segment, dict):
                raise ScriptLengthError("invalid_script_draft")
            narration = segment.get("narration")
            if (
                type(narration) is not str or not narration.isprintable()
                or not 1 <= len(narration) <= 500
                or "<" in narration or ">" in narration
            ):
                raise ScriptLengthError("invalid_script_draft")
            if section["key"] == "main":
                refs = segment.get("evidence_refs")
                if (
                    type(segment.get("fact_id")) is not int
                    or segment["fact_id"] <= 0
                    or not isinstance(refs, list) or not refs
                ):
                    raise ScriptLengthError("invalid_script_draft")
            else:
                if segment.get("fact_id") is not None or segment.get("evidence_refs") != []:
                    raise ScriptLengthError("invalid_script_draft")
            text_parts.append(narration)
            subtotal += len(_WORD.findall(narration))
        section_word_counts[section["key"]] = subtotal
    if draft.get("reviewed_fact_count") != len(sections[1]["segments"]):
        raise ScriptLengthError("invalid_script_draft")
    if draft.get("voiceover_text") != "\n\n".join(text_parts):
        raise ScriptLengthError("stale_script_draft")

    fingerprint = draft.get("input_fingerprint_sha256")
    if type(fingerprint) is not str or not _HASH.fullmatch(fingerprint):
        raise ScriptLengthError("stale_script_draft")
    canonical = {key: val for key, val in draft.items()
                 if key != "input_fingerprint_sha256"}
    try:
        encoded = json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        raise ScriptLengthError("invalid_script_draft") from None
    if sha256(encoded).hexdigest() != fingerprint:
        raise ScriptLengthError("stale_script_draft")

    plan = plan_spoken_text(
        draft["voiceover_text"], words_per_minute=words_per_minute,
    )
    return {
        **plan,
        "job_id": draft["job_id"],
        "dossier_version": draft["dossier_version"],
        "script_fingerprint_sha256": fingerprint,
        "section_word_counts": section_word_counts,
        "editorial_review_required": True,
    }


def require_script_length_before_tts(draft, *, words_per_minute=DEFAULT_WORDS_PER_MINUTE):
    """Fail closed when too short/long. Does NOT authorize paid TTS itself."""
    report = plan_script_draft_length(
        draft, words_per_minute=words_per_minute,
    )
    if not report["length_within_target"]:
        raise ScriptLengthError(report["status"])
    return report
