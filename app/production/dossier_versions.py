"""Make a new immutable-in-practice dossier version under a locked job row.

Caller MUST hold transaction.atomic() + SELECT ... FOR UPDATE on the
ProductionJob. Never edit rows of the preceding research version.
"""
from copy import deepcopy

from .models import Evidence, Fact, FactDossier, SourceReference


def fork_dossier(*, job, previous):
    """Copy sources, facts and evidence to a new standalone numbered snapshot.

    Mapping all foreign keys is necessary: evidence in a new version must
    reference sources within that SAME version. Verified status (if a prior
    reviewer set it) is only restored AFTER its supporting evidence is copied.
    This function does not verify or upgrade any fact.
    """
    dossier = FactDossier.objects.create(
        job=job, version=previous.version + 1 if previous else 1,
    )
    if previous is None:
        return dossier

    source_map = {}
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
        for link in sorted(old.evidence.all(), key=lambda item: item.pk):
            Evidence(
                fact=new, source=source_map[link.source_id],
                locator=link.locator, summary=link.summary, role=link.role,
            ).save()

        if old.verification_state == Fact.Verification.VERIFIED:
            new.verification_state = Fact.Verification.VERIFIED
            new.save(update_fields=["verification_state"])

    return dossier
