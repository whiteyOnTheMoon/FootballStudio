"""Automatic, bounded free Wikidata P115 venue enrichment for an owned job.

Follows an already imported, clearly identified club Q-ID; this cannot
create a club association from arbitrary user input. Stadium candidates
stay UNVERIFIED. Never fetches a venue website, uses Wikipedia as an
independent source, or synthesizes a human FactReview.
"""
from datetime import datetime, timezone
import re

from django.db import transaction

from .dossier_versions import fork_dossier
from .models import (
    Evidence, Fact, FactDossier, ProductionJob, SourceReference,
)
from .wikimedia_auto import AutoResearchError, _claims, _entity, _statement_value

_QID = re.compile(r"Q[1-9][0-9]{0,11}\Z")
_ENGLISH_STADIUM = re.compile(r"[^<>\r\n\t]{2,160}\Z")


def _year(snak):
    """Conservative qualifier date; unknown dates do not imply a current venue."""
    if not isinstance(snak, dict):
        return None
    value = snak.get("datavalue")
    time = value.get("value") if isinstance(value, dict) else None
    stamp = time.get("time") if isinstance(time, dict) else None
    if (
        type(stamp) is not str
        or not re.fullmatch(r"\+[0-9]{4}-[0-9]{2}-[0-9]{2}T00:00:00Z", stamp)
    ):
        return None
    return int(stamp[1:5])


def _current_statement(statement, current_year):
    """Reject historical, scheduled and ambiguous qualified P115 venues."""
    qualifiers = statement.get("qualifiers", {})
    if not isinstance(qualifiers, dict):
        return False
    for key, comparator in (
        ("P580", lambda year: year < current_year),
        ("P582", lambda year: year > current_year),
    ):
        if key not in qualifiers:
            continue
        claims = qualifiers[key]
        if not isinstance(claims, list) or len(claims) != 1:
            return False
        if (year := _year(claims[0])) is None or not comparator(year):
            return False
    return True


def _venue_qid(entity):
    rows = _claims(entity, "P115")
    current_year = datetime.now(timezone.utc).year
    grouped = {"preferred": set(), "normal": set()}
    for row in rows:
        if not _current_statement(row, current_year):
            continue
        value = _statement_value(row)
        qid = value.get("id") if isinstance(value, dict) else None
        if type(qid) is str and _QID.fullmatch(qid):
            grouped[row["rank"]].add(qid)

    chosen = grouped["preferred"] or grouped["normal"]
    if not chosen:
        raise AutoResearchError("no_stadium_candidate")
    if len(chosen) != 1:
        raise AutoResearchError("ambiguous_stadium")
    return next(iter(chosen))


def discover_wikidata_stadium(*, club_qid):
    """Read only fixed Wikidata EntityData URLs for club and stadium items."""
    if type(club_qid) is not str or not _QID.fullmatch(club_qid):
        raise AutoResearchError("invalid_club_qid")
    club = _entity(club_qid)
    venue_qid = _venue_qid(club)
    venue = _entity(venue_qid)
    labels = venue.get("labels")
    english = labels.get("en") if isinstance(labels, dict) else None
    name = english.get("value") if isinstance(english, dict) else None
    if (
        type(name) is not str or not _ENGLISH_STADIUM.fullmatch(name)
        or name != name.strip() or not name.isprintable()
    ):
        raise AutoResearchError("missing_stadium_label")
    return {
        "club_qid": club_qid,
        "venue_qid": venue_qid,
        "stadium_name": name,
        "club_url":
            f"https://www.wikidata.org/wiki/Special:EntityData/{club_qid}.json",
        "venue_url":
            f"https://www.wikidata.org/wiki/Special:EntityData/{venue_qid}.json",
        "retrieved_at": datetime.now(timezone.utc),
    }


def _latest(job):
    return FactDossier.objects.filter(job=job).order_by("-version").first()


def _already_stadium(dossier):
    return dossier.facts.filter(predicate="stadium_name").exists()


def enrich_wikimedia_stadium(*, owner, job_id, expected_version):
    """Fork a dossier once to add a structured, cited stadium fact candidate.

    Source discovery uses the exact *previously imported* auto club Q-ID.
    Owner/version checks occur BEFORE any network call. A repeated request
    after success reuses the latest dossier; prior human reviews are carried
    forward via fork_dossier, never overwritten or upgraded by this service.
    """
    owner_id = getattr(owner, "pk", None)
    if (
        type(owner_id) is not int or owner_id < 1
        or type(job_id) is not int or job_id < 1
        or type(expected_version) is not int or expected_version < 1
    ):
        raise AutoResearchError("invalid_request")
    job = ProductionJob.objects.filter(
        pk=job_id, owner_id=owner_id,
    ).first()
    if job is None:
        raise AutoResearchError("not_authorized")
    latest = _latest(job)
    if latest is None:
        raise AutoResearchError("no_auto_research")
    if _already_stadium(latest):
        return latest
    if latest.version != expected_version:
        raise AutoResearchError("stale_dossier")
    matches = list(latest.sources.filter(
        source_kind=SourceReference.Kind.WIKIDATA,
        title__startswith="[auto] ",
        external_id__regex=r"^Q[1-9][0-9]{0,11}$",
    ).order_by("pk")[:2])
    if len(matches) != 1:
        raise AutoResearchError("no_auto_research")
    club_source = matches[0]
    qid = club_source.external_id
    if club_source.url != (
        f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    ):
        raise AutoResearchError("invalid_club_source")

    candidate = discover_wikidata_stadium(club_qid=qid)

    with transaction.atomic():
        locked = ProductionJob.objects.select_for_update().get(
            pk=job.pk, owner_id=owner_id,
        )
        latest = _latest(locked)
        if latest is None:
            raise AutoResearchError("stale_dossier")
        if _already_stadium(latest):
            return latest
        if latest.version != expected_version:
            raise AutoResearchError("stale_dossier")
        source = latest.sources.filter(
            pk=club_source.pk, source_kind=SourceReference.Kind.WIKIDATA,
            external_id=qid, url=candidate["club_url"],
            title__startswith="[auto] ",
        ).first()
        if source is None:
            raise AutoResearchError("stale_dossier")

        dossier = fork_dossier(job=locked, previous=latest)
        linked = dossier.sources.get(
            url=candidate["club_url"],
            source_kind=SourceReference.Kind.WIKIDATA,
            external_id=qid,
        )
        venue_source = dossier.sources.filter(
            url=candidate["venue_url"],
            source_kind=SourceReference.Kind.WIKIDATA,
            external_id=candidate["venue_qid"],
        ).first()
        if venue_source is None:
            venue_source = SourceReference.objects.create(
                dossier=dossier, source_kind=SourceReference.Kind.WIKIDATA,
                url=candidate["venue_url"],
                title="Wikidata venue: " + candidate["stadium_name"][:230],
                external_id=candidate["venue_qid"],
                retrieved_at=candidate["retrieved_at"],
                access_state=SourceReference.Access.ACCESSIBLE,
            )
        name = candidate["stadium_name"]
        fact = Fact.objects.create(
            dossier=dossier, predicate="stadium_name", value=name,
            assertion_text=f"The club's home stadium is {name}.",
            verification_state=Fact.Verification.UNVERIFIED,
        )
        Evidence.objects.create(
            fact=fact, source=linked, role=Evidence.Role.UNKNOWN,
            locator=f"Wikidata {qid} · home venue (P115)",
            summary=(
                f"Item {qid} references venue {candidate['venue_qid']} "
                f"under P115; the English name is {name}. "
                "Automated structured candidate, not independently verified."
            ),
        )
        # The referenced venue item establishes the retrieved English label.
        # Both items are Wikidata, NOT two independent corroborating sources.
        Evidence.objects.create(
            fact=fact, source=venue_source, role=Evidence.Role.UNKNOWN,
            locator=f"Wikidata item {candidate['venue_qid']} · English label",
            summary=(
                f"English label {name} for venue item {candidate['venue_qid']}. "
                "Linked Wikidata metadata only; not a separate review."
            ),
        )
        return dossier
