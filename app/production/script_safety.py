"""Deterministic, fail-closed English script context for reviewed football facts.

Input is the already owner-scoped, serialized dossier snapshot produced by
load_fact_dossier(). These pure functions do NOT access models, databases,
URLs, networks, workers, LLMs or paid APIs. In particular, a source being
marked "accessible" or "official" is *never* enough for a factual voiceover.

Wording is from fixed templates and strictly shaped values. No free-form
source extract, reviewer note or unreviewed assertion becomes narration.
"""
from datetime import datetime
import re

from .safe_official_fetch import WebsiteFetchError, _checked_url


_KNOWN_PREDICATES = {
    "founded_year", "stadium_name", "competition_win",
    "league_membership", "standings_position",
}
_SEASON = re.compile(r"(?:18|19|20)\d{2}(?:/\d{2})?\Z")
_SEASON_RANGE = re.compile(r"(?:18|19|20)\d{2}/\d{2}")

# Fixed, non-factual transitions; never interpolate disputed dates or values.
_UNCERTAIN = {
    "founded_year": "The club's founding year has not been established by reviewed evidence.",
    "stadium_name": "The available evidence does not firmly establish the club's stadium.",
    "competition_win": "The available evidence does not establish this competition result.",
    "league_membership": "The club's participation in that season remains unconfirmed.",
    "standings_position": "The club's final position for that season remains unconfirmed.",
}
_CONFLICTED = {
    "founded_year": "Sources disagree about when the club was founded; a reliable year cannot yet be stated.",
    "stadium_name": "Sources give conflicting stadium information, so no single name can be stated confidently.",
    "competition_win": "Sources disagree about this competition result; it remains unresolved.",
    "league_membership": "Sources give conflicting accounts of league participation for this season.",
    "standings_position": "Sources disagree about the final league position for this season.",
}
_GENERIC_UNCERTAIN = "This part of the club's history needs further source verification."
_GENERIC_CONFLICT = "The available sources disagree; a reliable account has not yet been established."


def _plain(value, *, max_length=160):
    """A single-line, short, printable human-checked data value."""
    return (
        isinstance(value, str)
        and 2 <= len(value) <= max_length
        and value == value.strip()
        and value.isprintable()
        and "<" not in value
        and ">" not in value
        and not any(ch in value for ch in ("\r", "\n", "\t"))
    )


def _valid_season(value):
    if not isinstance(value, str) or not _SEASON.fullmatch(value):
        return False
    if "/" in value:
        first, last = value.split("/")
        return int(last) == (int(first) + 1) % 100
    return True


def _structured_sentence(predicate, value):
    """Use vetted structured values only, never untrusted assertion_text."""
    if predicate == "founded_year":
        if type(value) is int and 1800 <= value <= 2099:
            return f"The club was founded in {value}."
    elif predicate == "stadium_name":
        if _plain(value):
            return f"The club's home stadium is {value}."
    elif predicate == "competition_win":
        if (
            isinstance(value, dict) and set(value) == {"competition", "season"}
            and _plain(value["competition"])
            and _valid_season(value["season"])
        ):
            return f"The club won the {value['competition']} in {value['season']}."
    elif predicate == "league_membership":
        if (
            isinstance(value, dict) and set(value) == {"league", "season"}
            and _plain(value["league"]) and _valid_season(value["season"])
        ):
            return f"The club competed in the {value['league']} during the {value['season']} season."
    elif predicate == "standings_position":
        if (
            isinstance(value, dict)
            and set(value) == {"competition", "season", "position"}
            and _plain(value["competition"])
            and _valid_season(value["season"])
            and type(value["position"]) is int
            and 1 <= value["position"] <= 30
        ):
            position = value["position"]
            suffix = "th" if 11 <= position % 100 <= 13 else {
                1: "st", 2: "nd", 3: "rd",
            }.get(position % 10, "th")
            return (
                f"The club finished {position}{suffix} in the "
                f"{value['competition']} in {value['season']}."
            )
    return None


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None and moment.utcoffset() is not None else None


def _safe_url(value):
    if not isinstance(value, str):
        return None
    try:
        canonical, _host = _checked_url(value)
    except (WebsiteFetchError, ValueError, TypeError):
        return None
    return canonical if canonical == value else None


def _season_supported(value, evidence):
    """Match an entire season, never a prefix such as 2025 in 2025/26."""
    if not _valid_season(value):
        return False
    combined = f"{evidence.get('locator', '')} {evidence.get('summary', '')}"
    if not isinstance(combined, str):
        return False
    token = re.compile(r"(?<![0-9/])" + re.escape(value) + r"(?![0-9/])")
    if not token.search(combined):
        return False
    # Two incompatible season ranges in the same supporting description
    # are ambiguous without further human checking.
    return all(item == value for item in _SEASON_RANGE.findall(combined))


def _identifier(value):
    return type(value) is int and value > 0


def prepare_script_fact(fact, sources_by_id):
    """Return one safe, structured script unit without external side effects.

    'usable' is allowed only after a matching human FactReview and current
    accessible, concrete evidence. 'caution' and 'conflicted' have fixed
    non-factual English transitions. 'omit' never provides narration.
    """
    if not isinstance(fact, dict) or not isinstance(sources_by_id, dict):
        raise ValueError("A serialized fact and source mapping are required.")
    predicate = fact.get("predicate")
    if predicate not in _KNOWN_PREDICATES:
        predicate = None
    raw_value = fact.get("value")
    reference_value = raw_value if (
        type(raw_value) in (int, str, dict)
    ) else None
    season = raw_value.get("season") if isinstance(raw_value, dict) else None
    if not _valid_season(season):
        season = None

    evidence_refs = []
    qualified_support = []
    support_total = 0
    has_contradiction = False
    has_dangling = False
    for evidence in fact.get("evidence", []):
        if not isinstance(evidence, dict):
            has_dangling = True
            continue
        role = evidence.get("role")
        if role == "supports":
            support_total += 1
        if role == "contradicts":
            has_contradiction = True
        source = sources_by_id.get(evidence.get("source_id"))
        if not isinstance(source, dict):
            has_dangling = True
            continue
        url = _safe_url(source.get("url"))
        stamp = _time(source.get("retrieved_at"))
        provenance = source.get("manual_confirmation")
        evidence_refs.append({
            "source_id": source.get("id"),
            "role": role,
            "locator": evidence.get("locator") if isinstance(
                evidence.get("locator"), str
            ) else "",
            "url": url,
            "source_kind": source.get("source_kind"),
            "access_state": source.get("access_state"),
            "retrieved_at": source.get("retrieved_at"),
            "provenance": (
                "user_entered_checked"
                if isinstance(provenance, dict)
                and provenance.get("provenance") == "user_entered_checked"
                else "existing_source_reference"
            ),
            "source_checked_at": (
                provenance.get("checked_at")
                if isinstance(provenance, dict) else None
            ),
        })
        if (
            role == "supports"
            and source.get("access_state") == "accessible"
            and url is not None
            and stamp is not None
            and isinstance(evidence.get("locator"), str)
            and bool(evidence["locator"].strip())
            and isinstance(evidence.get("summary"), str)
            and bool(evidence["summary"].strip())
            and source.get("id") == evidence.get("source_id")
        ):
            qualified_support.append((evidence, stamp))

    status = fact.get("verification_state")
    review = fact.get("review")
    review_meta = None
    valid_review = False
    if isinstance(review, dict):
        review_meta = {
            "decision": review.get("decision"),
            "reviewer_id": review.get("reviewer_id"),
            "reviewed_at": review.get("reviewed_at"),
            "checked_source": review.get("checked_source") is True,
            "checked_season": review.get("checked_season") is True,
        }
        valid_review = (
            review.get("decision") == status
            and _identifier(review.get("reviewer_id"))
            and _time(review.get("reviewed_at")) is not None
            and isinstance(review.get("note"), str)
            and 30 <= len(review["note"].strip()) <= 500
        )

    reasons = []
    sentence = _structured_sentence(predicate, raw_value)
    if sentence is None:
        reasons.append("invalid_structured_value")
    if has_dangling:
        reasons.append("unmatched_source_reference")
    if status == "rejected":
        reasons.append("rejected")
        disposition, text = "omit", ""
    elif status == "conflicted" or has_contradiction:
        reasons.append("contradictory_evidence")
        disposition, text = "conflicted", _CONFLICTED.get(predicate, _GENERIC_CONFLICT)
    else:
        if status != "verified":
            reasons.append("no_verified_decision")
        if not valid_review or review.get("checked_source") is not True:
            reasons.append("missing_current_human_review")
        if not qualified_support:
            reasons.append("no_accessible_support")
        if support_total != len(qualified_support):
            reasons.append("incomplete_supporting_evidence")
        if has_dangling:
            reasons.append("incomplete_provenance")
        if status == "verified" and isinstance(review, dict) and valid_review:
            reviewed_at = _time(review["reviewed_at"])
            if any(stamp > reviewed_at for _, stamp in qualified_support):
                reasons.append("support_newer_than_review")

        if isinstance(raw_value, dict) and "season" in raw_value:
            if not isinstance(review, dict) or review.get("checked_season") is not True:
                reasons.append("season_not_checked")
            if not qualified_support or any(
                not _season_supported(raw_value["season"], evidence)
                for evidence, _stamp in qualified_support
            ):
                reasons.append("season_not_supported")
        if status == "verified" and not reasons:
            disposition, text = "usable", sentence
        else:
            disposition, text = "caution", _UNCERTAIN.get(predicate, _GENERIC_UNCERTAIN)

    return {
        "fact_id": fact.get("id"),
        "predicate": predicate or "other",
        "declared_status": status,
        "disposition": disposition,
        "narration": text,
        "reason_codes": reasons,
        # Metadata is for editors / citation tracking, NEVER narration.
        "reference_value": reference_value,
        "reference_season": season,
        "review": review_meta,
        "evidence_refs": evidence_refs,
    }


def prepare_script_preview(snapshot):
    """Produce an offline preview for one owner-scoped dossier snapshot.

    This helper itself performs no auth or DB lookup; callers MUST acquire
    a snapshot using load_fact_dossier(owner=..., job_id=..., version=...).
    """
    if not isinstance(snapshot, dict):
        raise ValueError("An owner-scoped serialized dossier is required.")
    sources = {
        row["id"]: row for row in snapshot.get("sources", [])
        if isinstance(row, dict) and _identifier(row.get("id"))
    }
    return {
        "job_id": snapshot.get("job_id"),
        "version": snapshot.get("version"),
        "units": [
            prepare_script_fact(item, sources)
            for item in snapshot.get("facts", [])
        ],
    }
