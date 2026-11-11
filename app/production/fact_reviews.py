"""Explicit human review of concrete evidence, never automatic truth inference.

An authorized job owner can mark an existing *already imported* source's
specific location as supporting/contradicting/context, then make a separate,
audited review decision. Every edit forks the entire latest dossier version;
old sources, fact states, evidence and review notes remain unchanged.
This module NEVER fetches URLs, runs LLMs, or publishes to the film script.
"""
from django.db import transaction

from .dossier_versions import fork_dossier
from .fact_proposals import _short_text
from .models import (
    Evidence, Fact, FactDossier, FactReview, ProductionJob, SourceReference,
)


_ROLES = {
    Evidence.Role.SUPPORTS,
    Evidence.Role.CONTRADICTS,
    Evidence.Role.CONTEXT_ONLY,
}
_DECISIONS = {
    Fact.Verification.VERIFIED,
    Fact.Verification.CONFLICTED,
    Fact.Verification.INSUFFICIENT,
    Fact.Verification.REJECTED,
}


def _current_fact(*, owner, job_id, expected_version, fact_id):
    """Caller must hold a transaction; the owner job row stays locked."""
    if type(expected_version) is not int or expected_version < 1:
        raise ValueError("The latest positive dossier version is required.")
    if type(fact_id) is not int or fact_id < 1:
        raise ValueError("An exact fact ID is required.")
    job = ProductionJob.objects.select_for_update().get(
        pk=job_id, owner=owner,
    )
    latest = FactDossier.objects.filter(job=job).order_by("-version").first()
    if latest is None:
        raise FactDossier.DoesNotExist("No research dossier available.")
    if latest.version != expected_version:
        raise ValueError("Stale dossier version; reload before reviewing facts.")
    fact = latest.facts.get(pk=fact_id)
    return job, latest, fact


def append_review_evidence(*, owner, job_id, expected_version, fact_id,
                           source_id, role, locator, summary,
                           source_checked=False):
    """Append one human-checked evidence record as a new, unverified version.

    Even 'supports' is NOT a verification decision. Any earlier formal
    review is invalidated in the NEW snapshot after changing its evidence;
    the old review remains documented in the preceding dossier version.
    """
    if source_checked is not True:
        raise ValueError("Confirm the specific source and locator were examined.")
    if role not in _ROLES:
        raise ValueError("Only supports, contradicts and context_only may be reviewed.")
    if type(source_id) is not int or source_id < 1:
        raise ValueError("An exact existing source ID is required.")
    place = _short_text(locator, "evidence locator", min_length=3, max_length=180)
    note = _short_text(summary, "evidence summary", min_length=15, max_length=350)

    with transaction.atomic():
        job, latest, fact = _current_fact(
            owner=owner, job_id=job_id, expected_version=expected_version,
            fact_id=fact_id,
        )
        source = latest.sources.get(pk=source_id)
        if source.access_state != SourceReference.Access.ACCESSIBLE:
            raise ValueError("Evidence sources must be accessible.")
        if fact.evidence.filter(
            source=source, role=role, locator=place, summary=note,
        ).exists():
            return latest

        dossier, sources, facts = fork_dossier(
            job=job, previous=latest, return_mappings=True,
        )
        new_fact = facts[fact.pk]
        Evidence.objects.create(
            fact=new_fact, source=sources[source.pk], role=role,
            locator=place, summary=note,
        )
        # Evidence was modified since the old review. Its past approval
        # cannot be inherited as approval for the new snapshot.
        FactReview.objects.filter(fact=new_fact).delete()
        if new_fact.verification_state != Fact.Verification.UNVERIFIED:
            new_fact.verification_state = Fact.Verification.UNVERIFIED
            new_fact.save(update_fields=["verification_state"])
        return dossier


def _evidence_status(fact):
    accessible_support = []
    accessible_contradictions = []
    any_contradiction = False
    for evidence in fact.evidence.select_related("source"):
        if evidence.role == Evidence.Role.CONTRADICTS:
            any_contradiction = True
        if evidence.source.access_state != SourceReference.Access.ACCESSIBLE:
            continue
        # A generic source pointer with no concrete locator is not evidence.
        if not evidence.locator.strip() or not evidence.summary.strip():
            continue
        if evidence.role == Evidence.Role.SUPPORTS:
            accessible_support.append(evidence)
        if evidence.role == Evidence.Role.CONTRADICTS:
            accessible_contradictions.append(evidence)
    return accessible_support, accessible_contradictions, any_contradiction


def decide_fact_review(*, owner, job_id, expected_version, fact_id,
                       decision, review_note, review_confirmed=False,
                       source_checked=False, season_checked=False):
    """Record an explicit, owner-attributed source assessment and decision.

    'verified' needs a real accessible supporting Evidence, explicit source
    inspection and no unresolved contradiction. Seasonal claims also need
    a checked season AND an actual supporting locator/summary naming it.
    Python does not perform semantic fact checking: this is a review record.
    """
    if review_confirmed is not True:
        raise ValueError("A conscious fact-review confirmation is required.")
    if decision not in _DECISIONS:
        raise ValueError("Select a supported explicit fact-review decision.")
    if type(source_checked) is not bool or type(season_checked) is not bool:
        raise ValueError("Explicit yes/no review-check fields are required.")
    note = _short_text(
        review_note, "review rationale", min_length=30, max_length=500,
    )

    with transaction.atomic():
        job, latest, fact = _current_fact(
            owner=owner, job_id=job_id, expected_version=expected_version,
            fact_id=fact_id,
        )
        support, contradictions, any_contradiction = _evidence_status(fact)
        if decision == Fact.Verification.VERIFIED:
            if not source_checked or not support:
                raise ValueError("Verified requires a checked accessible supporting locator.")
            if any_contradiction:
                raise ValueError("Unresolved contradictory evidence blocks verification.")
            if isinstance(fact.value, dict) and "season" in fact.value:
                if not season_checked:
                    raise ValueError("Seasonal claims require explicit season cross-check.")
                season = fact.value["season"]
                if not all(
                    season in (e.locator + " " + e.summary) for e in support
                ):
                    raise ValueError(
                        "Every supporting locator must identify the specific season."
                    )
        elif decision == Fact.Verification.CONFLICTED:
            if not source_checked or not support or not contradictions:
                raise ValueError("Conflicted requires checked supporting AND contradicting evidence.")
        elif decision == Fact.Verification.INSUFFICIENT:
            if support and any_contradiction:
                raise ValueError("Unresolved contradictions must be marked conflicted or rejected.")

        prior = FactReview.objects.filter(fact=fact).first()
        if (
            prior is not None and prior.decision == decision
            and prior.note == note
            and prior.checked_source == source_checked
            and prior.checked_season == season_checked
            and prior.reviewer_id == owner.pk
        ):
            return latest

        dossier, _sources, facts = fork_dossier(
            job=job, previous=latest, return_mappings=True,
        )
        new_fact = facts[fact.pk]
        # This is a fresh version: a different review decision may supersede
        # the copied one but the prior version remains an audit record.
        FactReview.objects.filter(fact=new_fact).delete()
        new_fact.verification_state = decision
        new_fact.save(update_fields=["verification_state"])
        FactReview.objects.create(
            fact=new_fact, reviewer=owner, decision=decision, note=note,
            checked_source=source_checked, checked_season=season_checked,
        )
        return dossier
