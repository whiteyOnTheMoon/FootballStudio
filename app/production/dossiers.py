"""Read-only, owner-scoped and serializable M2 fact dossier snapshots.

A snapshot contains references to evidence; it does not assert that the
sources were independently fact-checked. No HTTP endpoint is exposed.
"""
from .models import FactDossier, FactReview, SourceConfirmation


def _review_metadata(fact):
    """Expose recorded human decisions, not implied source trust."""
    try:
        review = fact.review
    except FactReview.DoesNotExist:
        return None
    return {
        "decision": review.decision,
        "reviewer_id": review.reviewer_id,
        "note": review.note,
        "checked_source": review.checked_source,
        "checked_season": review.checked_season,
        "reviewed_at": review.reviewed_at.isoformat(),
    }


def _manual_source_metadata(source):
    """One confirmed source's audit record, only in an owner-scoped snapshot."""
    try:
        confirmation = source.manual_confirmation
    except SourceConfirmation.DoesNotExist:
        return None
    return {
        "provenance": "user_entered_checked",
        "reviewer_id": confirmation.reviewer_id,
        "checked_at": confirmation.checked_at.isoformat(),
        "confirmed_domain": confirmation.confirmed_domain,
        "identity_confirmed": confirmation.identity_confirmed,
        "terms_confirmed": confirmation.terms_confirmed,
        "access_confirmed": confirmation.access_confirmed,
        "basis": confirmation.basis,
    }


def load_fact_dossier(*, owner, job_id, version):
    """Return one job version; an inaccessible job looks like a missing dossier.

    Raises FactDossier.DoesNotExist for unknown versions or other owners.
    """
    dossier = FactDossier.objects.select_related("job").get(
        job_id=job_id, job__owner=owner, version=version,
    )
    sources = list(dossier.sources.select_related("manual_confirmation").order_by("pk"))
    facts = dossier.facts.select_related("review").prefetch_related("evidence").order_by("pk")
    return {
        "job_id": dossier.job_id,
        "club_id": dossier.job.club_id,
        "club_name": dossier.job.club_name,
        "version": dossier.version,
        "created_at": dossier.created_at.isoformat(),
        "sources": [
            {
                "id": source.pk,
                "url": source.url,
                "source_kind": source.source_kind,
                "title": source.title,
                "external_id": source.external_id,
                "retrieved_at": source.retrieved_at.isoformat(),
                "access_state": source.access_state,
                "manual_confirmation": _manual_source_metadata(source),
            }
            for source in sources
        ],
        "facts": [
            {
                "id": fact.pk,
                "predicate": fact.predicate,
                "value": fact.value,
                "assertion_text": fact.assertion_text,
                "verification_state": fact.verification_state,
                "review": _review_metadata(fact),
                "evidence": [
                    {
                        "id": evidence.pk,
                        "source_id": evidence.source_id,
                        "locator": evidence.locator,
                        "summary": evidence.summary,
                        "role": evidence.role,
                    }
                    for evidence in sorted(fact.evidence.all(), key=lambda row: row.pk)
                ],
            }
            for fact in facts
        ],
    }
