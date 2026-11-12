"""FS-015a preparation contract. No model, network, database or billing calls.

The caller MUST first load an owner-scoped dossier snapshot; these pure helpers
only prepare a narrowly permitted input and validate a *candidate* response.
Validated candidates are NOT approved publication titles or persisted records.
"""
import re

from .script_safety import prepare_script_preview


class TitleContractError(ValueError):
    """Stable public error code, never a provider response or secret."""


def _printable(value, lower, upper):
    return (
        isinstance(value, str) and lower <= len(value) <= upper
        and value == value.strip() and value.isprintable()
        and not any(ch in value for ch in ("<", ">", "\\r", "\\n", "\\t"))
    )


def build_title_brief(snapshot, *, club_name):
    """Only human-reviewed, structurally safe script lines enter the brief.

    In particular: no unreviewed assertion, source article text, fact notes,
    unknown provider output, manually entered market estimates or hidden URLs.
    Returns a structured payload, NOT a string with instructions from a site.
    """
    if not _printable(club_name, 2, 160):
        raise TitleContractError("invalid_club_name")
    if not isinstance(snapshot, dict):
        raise TitleContractError("invalid_snapshot")
    preview = prepare_script_preview(snapshot)
    if type(preview["job_id"]) is not int or type(preview["version"]) is not int:
        raise TitleContractError("invalid_snapshot")
    safe = []
    for unit in preview["units"]:
        if unit["disposition"] != "usable":
            continue
        refs = [
            {"source_id": ref["source_id"], "url": ref["url"]}
            for ref in unit["evidence_refs"]
            if ref["role"] == "supports" and ref["url"] is not None
            and type(ref["source_id"]) is int
        ]
        if not refs or type(unit["fact_id"]) is not int:
            continue
        safe.append({
            "fact_id": unit["fact_id"],
            "sentence": unit["narration"],
            "supporting_sources": refs,
        })
        if len(safe) == 12:
            break
    if not safe:
        raise TitleContractError("no_reviewed_facts")
    return {
        "contract": "fs-015a-title-brief-v1",
        "job_id": preview["job_id"],
        "dossier_version": preview["version"],
        "club_name": club_name,
        "language": "en",
        "requested_titles": 3,
        "reviewed_facts": safe,
        "editorial_review_required": True,
    }


def validate_title_candidates(payload, *, club_name, reviewed_sentences):
    """Fail closed on malformed/duplicate/ungrounded AI output.

    This is syntactic grounding, not independent fact verification. A human
    still must select or edit a title; do not automatically publish candidates.
    """
    if not _printable(club_name, 2, 160):
        raise TitleContractError("invalid_club_name")
    if not isinstance(payload, dict) or set(payload) != {"titles"}:
        raise TitleContractError("invalid_response")
    titles = payload["titles"]
    if not isinstance(titles, list) or len(titles) != 3:
        raise TitleContractError("expected_three_titles")
    if not isinstance(reviewed_sentences, list) or not reviewed_sentences or any(
        not isinstance(x, str) for x in reviewed_sentences
    ):
        raise TitleContractError("missing_reviewed_context")
    known_numbers = set()
    for sentence in reviewed_sentences:
        known_numbers.update(re.findall(r"(?<!\\w)\\d+(?!\\w)", sentence))
    seen = set()
    for title in titles:
        if not _printable(title, 12, 180):
            raise TitleContractError("invalid_title")
        if club_name.casefold() not in title.casefold():
            raise TitleContractError("club_name_missing")
        signature = " ".join(title.casefold().split())
        if signature in seen:
            raise TitleContractError("duplicate_titles")
        seen.add(signature)
        if not set(re.findall(r"(?<!\\w)\\d+(?!\\w)", title)) <= known_numbers:
            raise TitleContractError("unreviewed_number")
    return tuple(titles)
