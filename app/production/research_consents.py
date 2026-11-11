"""Audited one-time research consent without ANY network or task execution.

The caller is the authenticated owner. Each POST takes a PostgreSQL job
row lock before version/source validation, idempotency, abuse checks and
one insert. No crawler or worker is imported anywhere in this module.

These records are *not* automatically executable: a future worker must
separately authenticate its authorization, revalidate current source and
owner, robots/TLS/DNS/terms and acquire a bounded single-use execution lock.
"""
from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from .models import (
    FactDossier, OfficialResearchRequest, ProductionJob, SourceReference,
)
from .official_site_preflight import plan_confirmed_official_source


_CONSENT_TTL = timedelta(minutes=15)
_RATE_WINDOW = timedelta(hours=24)
_MAX_USER_CONSENTS_PER_DAY = 3
_MAX_SAME_DOMAIN_PER_DAY = 1


class ResearchConsentInvalid(ValueError):
    pass


class ResearchConsentStale(ValueError):
    pass


class ResearchConsentConflict(ValueError):
    pass


class ResearchConsentRateLimited(ValueError):
    pass


def record_one_time_research_consent(
    *, owner, job_id, source_id, expected_version, request_key,
    domain_rechecked=False, terms_rechecked=False, one_time_approved=False,
):
    """Return (request, created) after validated, serialized DB-only consent.

    The caller supplies only the *existing* source_id, expected version and
    v4 retry key: the HTTPS URL, domain and context come from the owner
    dossier's signed-off SourceReference, never from POST data.
    """
    if not all((
        domain_rechecked is True,
        terms_rechecked is True,
        one_time_approved is True,
    )):
        raise ResearchConsentInvalid("Explicit fresh consent is required.")
    if (
        type(job_id) is not int or job_id <= 0
        or type(source_id) is not int or source_id <= 0
        or type(expected_version) is not int or expected_version < 1
        or expected_version >= 1_000_000_000
        or not isinstance(request_key, UUID) or request_key.version != 4
    ):
        raise ResearchConsentInvalid("Invalid job, source, version or retry key.")

    with transaction.atomic():
        # For PostgreSQL this lock coordinates all owner-scoped dossier
        # writers and simultaneous approvals from multiple browser tabs.
        job = ProductionJob.objects.select_for_update().get(
            pk=job_id, owner=owner,
        )
        latest = FactDossier.objects.filter(job=job).order_by("-version").first()
        if latest is None or latest.version != expected_version:
            raise ResearchConsentStale("The research dossier has changed.")

        source = SourceReference.objects.filter(
            pk=source_id, dossier=latest,
        ).select_related("manual_confirmation", "dossier__job").first()
        if source is None:
            raise ResearchConsentInvalid("Source does not belong to the current dossier.")
        plan = plan_confirmed_official_source(
            source, owner_id=owner.pk, current_dossier_id=latest.pk,
        )
        if plan is None:
            raise ResearchConsentInvalid("Source is not confirmed for manual research.")

        now = timezone.now()
        previous = OfficialResearchRequest.objects.filter(
            job=job, request_key=request_key,
        ).first()
        if previous is not None:
            if (
                previous.source_id == source.pk
                and previous.expected_version == expected_version
                and previous.confirmed_url == plan.source_url
                and previous.confirmed_domain == plan.domain
                and previous.context == plan.context
                and previous.requested_by_id == owner.pk
                and previous.domain_rechecked
                and previous.terms_rechecked
                and previous.one_time_approved
                and previous.status == OfficialResearchRequest.Status.PENDING
                and previous.expires_at > now
            ):
                return previous, False
            raise ResearchConsentConflict(
                "This submission was already used, cancelled or expired."
            )

        recent = OfficialResearchRequest.objects.filter(
            requested_by=owner,
            consented_at__gte=now - _RATE_WINDOW,
        )
        if recent.count() >= _MAX_USER_CONSENTS_PER_DAY:
            raise ResearchConsentRateLimited("Daily consent limit reached.")
        if recent.filter(confirmed_domain=plan.domain).exists():
            raise ResearchConsentRateLimited("This domain was approved recently.")

        active = OfficialResearchRequest.objects.filter(
            job=job,
            status=OfficialResearchRequest.Status.PENDING,
            expires_at__gt=now,
        )
        if active.exists():
            raise ResearchConsentConflict("An unexpired request already exists for this job.")

        # Only after every failed request has exited without mutation: close
        # naturally expired pending entries before satisfying DB uniqueness.
        OfficialResearchRequest.objects.filter(
            job=job,
            status=OfficialResearchRequest.Status.PENDING,
            expires_at__lte=now,
        ).update(status=OfficialResearchRequest.Status.EXPIRED)

        row = OfficialResearchRequest(
            job=job, source=source, requested_by=owner,
            request_key=request_key, expected_version=latest.version,
            confirmed_url=plan.source_url, confirmed_domain=plan.domain,
            context=plan.context, domain_rechecked=True,
            terms_rechecked=True, one_time_approved=True,
            consented_at=now, expires_at=now + _CONSENT_TTL,
            status=OfficialResearchRequest.Status.PENDING,
            attempt_count=0, max_pages=4,
        )
        row.save()
        return row, True


def cancel_one_time_research_consent(*, owner, job_id, request_id):
    """Owner-only explicit cancellation or age-based expiry, never a fetch."""
    if (
        type(job_id) is not int or job_id <= 0
        or type(request_id) is not int or request_id <= 0
    ):
        raise ResearchConsentInvalid("Invalid request.")
    with transaction.atomic():
        job = ProductionJob.objects.select_for_update().get(
            pk=job_id, owner=owner,
        )
        row = OfficialResearchRequest.objects.filter(
            pk=request_id, job=job, requested_by=owner,
        ).first()
        if row is None:
            raise OfficialResearchRequest.DoesNotExist
        if row.status != OfficialResearchRequest.Status.PENDING:
            return row, False
        now = timezone.now()
        if row.expires_at <= now:
            row.status = OfficialResearchRequest.Status.EXPIRED
            OfficialResearchRequest.objects.filter(pk=row.pk).update(status=row.status)
        else:
            row.status = OfficialResearchRequest.Status.CANCELLED
            row.cancelled_at = now
            OfficialResearchRequest.objects.filter(pk=row.pk).update(
                status=row.status, cancelled_at=now,
            )
        return row, True
