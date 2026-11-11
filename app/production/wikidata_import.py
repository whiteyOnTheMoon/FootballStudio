"""Explicit, owner-scoped Wikidata source import for a selected production job.

This is a source *reference* import, not a fact or verified club identity.
It never runs on an HTTP request or worker automatically. A future UI must
require the user to confirm the specific Wikidata entity before calling it.
"""
from datetime import datetime

from django.db import transaction

from .dossier_versions import fork_dossier
from .models import FactDossier, ProductionJob, SourceReference
from .wikidata import (
    WikidataLookupError,
    fetch_wikidata_profile,
    validate_wikidata_qid,
)


def _latest_dossier(job):
    return FactDossier.objects.filter(job=job).order_by("-version").first()


def _has_entity(dossier, qid):
    return (
        dossier is not None
        and dossier.sources.filter(
            source_kind=SourceReference.Kind.WIKIDATA, external_id=qid,
        ).exists()
    )


def _validate_profile(profile, qid):
    """Only allow adapter-origin metadata, never arbitrary source URLs."""
    expected_url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    if not isinstance(profile, dict) or any((
        profile.get("provider") != "wikidata",
        profile.get("entity_id") != qid,
        profile.get("source_url") != expected_url,
    )):
        raise WikidataLookupError("invalid_response")
    label = profile.get("label_en")
    if label is not None and (not isinstance(label, str) or len(label) > 250):
        raise WikidataLookupError("invalid_response")
    try:
        retrieved_at = datetime.fromisoformat(profile["fetched_at"])
    except (ValueError, TypeError, KeyError):
        raise WikidataLookupError("invalid_response") from None
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise WikidataLookupError("invalid_response")
    return expected_url, label or f"Wikidata entity {qid}", retrieved_at


def import_wikidata_source(*, owner, job_id, qid, identity_confirmed=False):
    """Save one source for an explicitly identified club, or reuse latest.

    Requires a *separately confirmed* identity association; neither a Q-ID
    nor a name match alone is proof that the entity is the selected club.
    Only the ProductionJob owner may call this service for that job.
    Returns the FactDossier, whose version increments only on new imports.
    The read-before-network check avoids redundant free public API calls;
    the lock prevents concurrent requests from creating duplicate versions.
    """
    if identity_confirmed is not True:
        raise ValueError("Explicit Wikidata entity association confirmation required.")
    validate_wikidata_qid(qid)

    # Fail before making an external call if the job is not owned by caller.
    job = ProductionJob.objects.get(pk=job_id, owner=owner)
    latest = _latest_dossier(job)
    if _has_entity(latest, qid):
        return latest

    # No database writes or row locks across network I/O.
    profile = fetch_wikidata_profile(qid)
    url, title, retrieved_at = _validate_profile(profile, qid)

    # PostgreSQL serializes concurrent version assignment for this job.
    with transaction.atomic():
        locked_job = ProductionJob.objects.select_for_update().get(
            pk=job_id, owner=owner,
        )
        latest = _latest_dossier(locked_job)
        if _has_entity(latest, qid):
            return latest
        dossier = fork_dossier(job=locked_job, previous=latest)
        source = SourceReference(
            dossier=dossier, url=url,
            source_kind=SourceReference.Kind.WIKIDATA,
            title=title, external_id=qid,
            retrieved_at=retrieved_at,
            access_state=SourceReference.Access.ACCESSIBLE,
        )
        source.full_clean()
        source.save()
        return dossier
