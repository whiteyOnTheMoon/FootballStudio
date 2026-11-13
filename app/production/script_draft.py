"""FS-016a: deterministic, review-only English script draft from an owned dossier.

No LLM, network, paid API, persistence or producer queue. The only factual
voiceover sentences come from the existing strict, typed script-safety rules.
Unverified, disputed and rejected input is NEVER interpolated into narration.
"""
from hashlib import sha256
import json

from django.core.exceptions import ObjectDoesNotExist

from .dossiers import load_fact_dossier
from .models import ProductionJob
from .script_safety import prepare_script_preview


class ScriptDraftError(ValueError):
    """Stable error code, never source text or private metadata."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


_OPENING = (
    "What can verified sources tell us about this football club? "
    "We begin with the facts that have been reviewed."
)
_CLOSING = (
    "These are the facts supported by the reviewed sources in this draft. "
    "Further research may be needed before a complete documentary can be made."
)


def _plain(value, *, minimum, maximum):
    return (
        isinstance(value, str) and minimum <= len(value) <= maximum
        and value == value.strip() and value.isprintable()
        and "<" not in value and ">" not in value
    )


def _segment(*, segment_id, narration, fact_id=None, evidence_refs=None):
    return {
        "id": segment_id,
        "narration": narration,
        "fact_id": fact_id,
        "evidence_refs": evidence_refs or [],
    }


def build_script_draft(snapshot, *, club_name, selected_title):
    """Build an UNAPPROVED English script draft, pure and reproducible.

    Caller must first retrieve an owner-scoped snapshot. selected_title is
    unreviewed editorial metadata and is never spoken as a factual claim.
    A zero-fact dossier is rejected rather than padded with invented history.
    """
    if (
        not isinstance(snapshot, dict)
        or type(snapshot.get("job_id")) is not int or snapshot["job_id"] <= 0
        or type(snapshot.get("version")) is not int or snapshot["version"] <= 0
        or not isinstance(snapshot.get("facts"), list)
        or not isinstance(snapshot.get("sources"), list)
        or not _plain(club_name, minimum=2, maximum=160)
        or snapshot.get("club_name") != club_name
        or not _plain(selected_title, minimum=4, maximum=180)
    ):
        raise ScriptDraftError("invalid_input")
    try:
        preview = prepare_script_preview(snapshot)
    except (KeyError, TypeError, ValueError):
        raise ScriptDraftError("invalid_dossier") from None
    evidence_segments = []
    unresolved = []
    excluded = []
    seen_fact_ids = set()
    for unit in preview["units"]:
        fact_id = unit["fact_id"]
        if type(fact_id) is not int or fact_id <= 0 or fact_id in seen_fact_ids:
            raise ScriptDraftError("invalid_fact_id")
        seen_fact_ids.add(fact_id)
        disposition = unit["disposition"]
        if disposition == "usable":
            refs = []
            seen_refs = set()
            for ref in unit["evidence_refs"]:
                if (
                    ref["role"] != "supports" or type(ref["source_id"]) is not int
                    or ref["source_id"] <= 0 or not isinstance(ref["url"], str)
                    or not ref["url"].startswith("https://")
                ):
                    continue
                key = (ref["source_id"], ref["url"])
                if key not in seen_refs:
                    refs.append({"source_id": key[0], "url": key[1]})
                    seen_refs.add(key)
            if not refs or not _plain(unit["narration"], minimum=2, maximum=500):
                raise ScriptDraftError("invalid_reviewed_unit")
            evidence_segments.append(_segment(
                segment_id=f"fact-{fact_id}",
                narration=unit["narration"],
                fact_id=fact_id,
                evidence_refs=refs,
            ))
        elif disposition in ("caution", "conflicted"):
            unresolved.append({
                "fact_id": fact_id, "disposition": disposition,
                "reason_codes": list(unit["reason_codes"]),
            })
        elif disposition == "omit":
            excluded.append({"fact_id": fact_id, "reason_codes": list(unit["reason_codes"])})
        else:
            raise ScriptDraftError("invalid_disposition")
    if not evidence_segments:
        raise ScriptDraftError("no_reviewed_facts")

    sections = [
        {"key": "opening", "segments": [
            _segment(segment_id="opening", narration=_OPENING),
        ]},
        {"key": "main", "segments": evidence_segments},
        {"key": "closing", "segments": [
            _segment(segment_id="closing", narration=_CLOSING),
        ]},
    ]
    voiceover_text = "\n\n".join(
        segment["narration"]
        for section in sections for segment in section["segments"]
    )
    result = {
        "schema": "fs-016a-offline-script-v1",
        "job_id": snapshot["job_id"],
        "dossier_version": snapshot["version"],
        "club_name": club_name,
        "selected_title_for_review": selected_title,
        "language": "en",
        "mode": "offline_reviewed_facts_only",
        "sections": sections,
        "voiceover_text": voiceover_text,
        "unresolved": unresolved,
        "excluded": excluded,
        "reviewed_fact_count": len(evidence_segments),
        "editorial_review_required": True,
        "ready_for_tts": False,
    }
    # All content needed for downstream invalidation, including title and
    # reference URLs, is hashed; do not hash arbitrary raw source passages.
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result["input_fingerprint_sha256"] = sha256(canonical.encode("utf-8")).hexdigest()
    return result


def load_job_script_draft(*, owner, job_id, version):
    """Owner-only read of job + requested dossier version; no DB writes."""
    owner_id = getattr(owner, "pk", None)
    if (
        type(owner_id) is not int or owner_id <= 0
        or type(job_id) is not int or job_id <= 0
        or type(version) is not int or version <= 0
    ):
        raise ScriptDraftError("invalid_request")
    job = ProductionJob.objects.filter(pk=job_id, owner_id=owner_id).first()
    if job is None:
        raise ScriptDraftError("not_authorized")
    if job.language != "en":
        raise ScriptDraftError("unsupported_language")
    try:
        snapshot = load_fact_dossier(owner=owner, job_id=job_id, version=version)
    except ObjectDoesNotExist:
        raise ScriptDraftError("dossier_not_found") from None
    return build_script_draft(
        snapshot, club_name=job.club_name, selected_title=job.title,
    )
