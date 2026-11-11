"""Make a new immutable-in-practice dossier version under a locked job row.

Caller MUST hold transaction.atomic() + SELECT ... FOR UPDATE on the
ProductionJob. Never edit rows of the preceding research version.
"""
from copy import deepcopy

from .models import Evidence, Fact, FactDossier, FactReview, SourceConfirmation, SourceReference


def fork_dossier(*, job, previous, return_mappings=False):
    """Copy sources, facts and evidence to a new standalone numbered snapshot.

    Mapping all foreign keys is necessary: evidence in a new version must
    reference sources within that SAME version. Verified status (if a prior
    reviewer set it) is only restored AFTER its supporting evidence is copied.
    This function does not verify or upgrade any fact. Optional return_mappings\n    returns remapped sources and facts, keyed by the previous row IDs.\n    Existing fact review decisions are carried into the new snapshot.
    """
    dossier = FactDossier.objects.create(
        job=job, version=previous.version + 1 if previous else 1,
    )
    source_map, fact_map = {}, {}
    if previous is None:
        return (dossier, source_map, fact_map) if return_mappings else dossier

    for old in previous.sources.order_by("pk"):
        new = SourceReference(
            dossier=dossier,
            url=old.url,
            source_kind=old.source_kind,
            title=old.title,
            external_id=old.external_id,
            retrieved_at=old.retrieved_at,
            access_state=old.access_state,
        )
        new.full_clean()
        new.save()
        source_map[old.pk] = new
        original_confirmation = SourceConfirmation.objects.filter(source=old).first()
        if original_confirmation is not None:
            SourceConfirmation.objects.create(
                source=new,
                reviewer=original_confirmation.reviewer,
                checked_at=original_confirmation.checked_at,
                confirmed_domain=original_confirmation.confirmed_domain,
                identity_confirmed=original_confirmation.identity_confirmed,
                terms_confirmed=original_confirmation.terms_confirmed,
                access_confirmed=original_confirmation.access_confirmed,
                basis=original_confirmation.basis,
            )

    for old in previous.facts.prefetch_related("evidence").order_by("pk"):
        new = Fact(
            dossier=dossier,
            predicate=old.predicate,
            value=deepcopy(old.value),
            assertion_text=old.assertion_text,
            verification_state=(
                Fact.Verification.UNVERIFIED
                if old.verification_state == Fact.Verification.VERIFIED
                else old.verification_state
            ),
        )
        new.save()
        fact_map[old.pk] = new
        for link in sorted(old.evidence.all(), key=lambda item: item.pk):
            Evidence(
                fact=new, source=source_map[link.source_id],
                locator=link.locator, summary=link.summary, role=link.role,
            ).save()

        if old.verification_state == Fact.Verification.VERIFIED:
            new.verification_state = Fact.Verification.VERIFIED
            new.save(update_fields=["verification_state"])

        # Review metadata is tied to one fact version. Copy it exactly,
        # including the original reviewer and date; never backdate new reviews.
        old_review = FactReview.objects.filter(fact=old).first()
        if old_review is not None:
            FactReview.objects.create(
                fact=new, reviewer=old_review.reviewer,
                decision=old_review.decision, note=old_review.note,
                checked_source=old_review.checked_source,
                checked_season=old_review.checked_season,
                reviewed_at=old_review.reviewed_at,
            )

    return (dossier, source_map, fact_map) if return_mappings else dossier
