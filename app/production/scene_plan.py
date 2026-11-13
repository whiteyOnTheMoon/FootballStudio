"""FS-016c offline scene plan from a trusted, fingerprint-checked script draft.

No network, media download, TTS, FFmpeg or paid APIs. Duration is an estimate,
not an audio-derived timestamp. Every factual scene preserves source references.
"""
from hashlib import sha256
import json

from .script_length import (
    DEFAULT_WORDS_PER_MINUTE, ScriptLengthError, _WORD,
    plan_script_draft_length,
)


class ScenePlanError(ValueError):
    """Stable codes; no narration or secret material in errors."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def build_scene_plan(draft, *, words_per_minute=DEFAULT_WORDS_PER_MINUTE):
    """Prepare storyboard scenes with explicitly non-cleared fallback visuals.

    Accept only internal FS-016a drafts from an owner-scoped caller. An intact
    fingerprint is a consistency check, not proof of authorization or review.
    """
    try:
        length = plan_script_draft_length(
            draft, words_per_minute=words_per_minute,
        )
    except ScriptLengthError as exc:
        raise ScenePlanError(exc.code) from None

    scenes = []
    seen_ids = set()
    elapsed_ms = 0
    for section in draft["sections"]:
        for segment in section["segments"]:
            segment_id = segment.get("id")
            if (
                type(segment_id) is not str or not segment_id
                or len(segment_id) > 90 or not segment_id.isascii()
                or not all(char.isalnum() or char in "-_" for char in segment_id)
                or segment_id in seen_ids
            ):
                raise ScenePlanError("invalid_segment_id")
            seen_ids.add(segment_id)
            fact_id = segment.get("fact_id")
            references = segment.get("evidence_refs")
            if section["key"] == "main":
                if segment_id != f"fact-{fact_id}":
                    raise ScenePlanError("invalid_segment_id")
                if any(
                    not isinstance(ref, dict)
                    or type(ref.get("source_id")) is not int
                    or ref["source_id"] <= 0
                    or not isinstance(ref.get("url"), str)
                    or not ref["url"].startswith("https://")
                    for ref in references
                ):
                    raise ScenePlanError("invalid_evidence_refs")
            elif segment_id != section["key"]:
                raise ScenePlanError("invalid_segment_id")

            words = len(_WORD.findall(segment["narration"]))
            if not words:
                raise ScenePlanError("empty_scene")
            # Cumulative exact counts prevent each-scene rounding from
            # introducing accumulating gaps/overlaps between neighboring scenes.
            end_ms = round(
                (sum(scene["word_count"] for scene in scenes) + words)
                * 60_000 / words_per_minute
            )
            if end_ms <= elapsed_ms:
                raise ScenePlanError("invalid_duration")
            scenes.append({
                "scene_number": len(scenes) + 1,
                "segment_id": segment_id,
                "section": section["key"],
                "narration": segment["narration"],
                "fact_id": fact_id,
                "evidence_refs": references,
                "word_count": words,
                "start_ms_estimate": elapsed_ms,
                "end_ms_estimate": end_ms,
                "duration_ms_estimate": end_ms - elapsed_ms,
                "visual": {
                    "kind": "original_text_card_placeholder",
                    "requires_editorial_review": True,
                    "external_media_selected": False,
                    "rights_cleared": False,
                },
            })
            elapsed_ms = end_ms

    if len(scenes) < 3 or len(scenes) > 2002:
        raise ScenePlanError("invalid_scene_count")
    if sum(scene["word_count"] for scene in scenes) != length["word_count"]:
        raise ScenePlanError("inconsistent_length")
    result = {
        "schema": "fs-016c-scene-plan-v1",
        "job_id": draft["job_id"],
        "dossier_version": draft["dossier_version"],
        "language": "en",
        "source_script_fingerprint_sha256": length["script_fingerprint_sha256"],
        "words_per_minute": words_per_minute,
        "estimated_total_ms": elapsed_ms,
        "script_length_status": length["status"],
        "scenes": scenes,
        "unresolved_fact_ids": [
            item["fact_id"] for item in draft["unresolved"]
        ],
        "editorial_review_required": True,
        "ready_for_tts": False,
        "ready_for_render": False,
    }
    encoded = json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    result["plan_fingerprint_sha256"] = sha256(encoded).hexdigest()
    return result
