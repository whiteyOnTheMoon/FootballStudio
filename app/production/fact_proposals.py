"""Manual, source-bound atomic fact proposals: deliberately NEVER auto-verified.

Fact proposals refer only to already-imported *official club/league* source
references in an owner-scoped dossier. No network, UI, LLM or article text
handling occurs. One exact prior version and source are required to avoid
attaching claims to stale or unrelated research snapshots.
"""
from datetime import datetime
import re

from django.db import transaction
from django.utils import timezone

from .dossier_versions import fork_dossier
from .models import Evidence, Fact, FactDossier, ProductionJob, SourceReference


_ALLOWED_SOURCES = {
    SourceReference.Kind.CLUB_OFFICIAL,
    SourceReference.Kind.LEAGUE_OFFICIAL,
}
_ALLOWED_PREDICATES = {
    "founded_year", "stadium_name", "competition_win",
    "league_membership", "standings_position",
}
_SEASON = re.compile(r"(?:18|19|20)[0-9]{2}(?:/[0-9]{2})?\Z")


def _short_text(value, label, *, min_length, max_length):
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise ValueError(f"{label} must be concise text.")
    normalized = " ".join(value.split())
    if (
        len(normalized) < min_length or len(normalized) > max_length
        or any(ord(char) < 32 or ord(char) == 127 for char in normalized)
        or "<" in normalized
    ):
        raise ValueError(f"{label} must be concise plain text.")
    return normalized


def _season(value):
    if not isinstance(value, str) or not _SEASON.fullmatch(value):
        raise ValueError("A valid season, e.g. 2025/26 or 2025, is required.")
    if "/" in value:
        start, ending = value.split("/")
        if int(ending) != (int(start) + 1) % 100:
            raise ValueError("Season years must be consecutive.")
    return value


def _value(predicate, value):
    if predicate not in _ALLOWED_PREDICATES:
        raise ValueError("Unsupported atomic football fact type.")
    if predicate == "founded_year":
        if type(value) is not int or not 1800 <= value <= datetime.now().year:
            raise ValueError("A real founded year is required.")
        return value
    if predicate == "stadium_name":
        return _short_text(value, "stadium name", min_length=2, max_length=160)

    fields = (
        ("competition", "season")
        if predicate == "competition_win"
        else ("league", "season") if predicate == "league_membership"
        else ("competition", "season", "position")
    )
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError("Structured fact fields must match the selected predicate.")
    result = {}
    for field in fields:
        if field == "season":
            result["season"] = _season(value["season"])
        elif field == "position":
            position = value["position"]
            if type(position) is not int or not 1 <= position <= 30:
                raise ValueError("An integer standings position from 1 to 30 is required.")
            result["position"] = position
        else:
            result[field] = _short_text(
                value[field], field, min_length=2, max_length=160,
            )
    return result


def _matching_source(dossier, source):
    candidates = dossier.sources.filter(
        url=source.url, source_kind=source.source_kind,
        retrieved_at=source.retrieved_at,
        access_state=SourceReference.Access.ACCESSIBLE,
    )
    return candidates.order_by("pk").first()


def _matching_proposal(dossier, source, *, predicate, value, statement,
                       locator, summary):
    if dossier is None or source is None:
        return False
    possible = dossier.facts.filter(
        predicate=predicate, assertion_text=statement,
        verification_state=Fact.Verification.UNVERIFIED,
    ).order_by("pk")
    for fact in possible:
        if fact.value != value:
            continue
        if fact.evidence.filter(
            source=source, locator=locator, summary=summary,
            role=Evidence.Role.UNKNOWN,
        ).exists():
            return True
    return False


def propose_official_fact(*, owner, job_id, expected_version, source_id,
                          predicate, value, assertion_text, locator,
                          evidence_summary):
    """Add one unverified fact + evidence in a new complete dossier snapshot.

    A client must supply the *currently displayed* dossier version and
    source ID. A repeated identical proposal may return the latest snapshot;
    a stale, changed proposal is rejected. Source URL alone is not evidence.
    The evidence role stays UNKNOWN until human content review.
    """
    if type(expected_version) is not int or expected_version < 1:
        raise ValueError("An explicit positive dossier version is required.")
    if type(source_id) is not int or source_id < 1:
        raise ValueError("An existing source reference ID is required.")
    normalized_value = _value(predicate, value)
    statement = _short_text(
        assertion_text, "assertion", min_length=10, max_length=350,
    )
    located = _short_text(locator, "evidence locator", min_length=3, max_length=180)
    summary = _short_text(
        evidence_summary, "evidence summary", min_length=10, max_length=350,
    )

    with transaction.atomic():
        job = ProductionJob.objects.select_for_update().get(
            pk=job_id, owner=owner,
        )
        base = FactDossier.objects.filter(
            job=job, version=expected_version,
        ).first()
        if base is None:
            raise FactDossier.DoesNotExist("Requested dossier version was not found.")
        source = base.sources.filter(pk=source_id).first()
        if source is None:
            raise SourceReference.DoesNotExist("Source is outside selected dossier.")
        if source.source_kind not in _ALLOWED_SOURCES or (
            source.access_state != SourceReference.Access.ACCESSIBLE
        ):
            raise ValueError("Fact proposals require an accessible official source.")
        latest = FactDossier.objects.filter(job=job).order_by("-version").first()
        matched = _matching_source(latest, source)
        if _matching_proposal(
            latest, matched, predicate=predicate, value=normalized_value,
            statement=statement, locator=located, summary=summary,
        ):
            return latest
        if latest.pk != base.pk:
            raise ValueError("Stale dossier version; reload before proposing facts.")

        dossier = fork_dossier(job=job, previous=latest)
        new_source = _matching_source(dossier, source)
        if new_source is None:
            raise ValueError("Source was not carried forward into the new dossier.")
        fact = Fact(
            dossier=dossier, predicate=predicate, value=normalized_value,
            assertion_text=statement,
            verification_state=Fact.Verification.UNVERIFIED,
        )
        fact.save()
        Evidence(
            fact=fact, source=new_source, locator=located,
            summary=summary, role=Evidence.Role.UNKNOWN,
        ).save()
        return dossier
