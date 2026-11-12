"""Explicit operator-run, single-use official research execution.

NO HTTP VIEW, queue, scheduled task or automatic scan invokes this module.
Only the separate management command can call execute_one_time_research().

Claim under a PostgreSQL job row lock, consuming the sole attempt and lease
BEFORE any robots/DNS/HTTPS call. Release locks for network activity. A fresh
DB-backed permit is required before EVERY individual external request, and
results commit only when the lease, dossier version and source fingerprint
remain unchanged. A failure never auto-retries the same consent.

Source bodies and article prose are NEVER saved. Only <=4 validated HTML
page URLs, titles, <=5 headings, timestamps and 'unverified' metadata.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
import time
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from .dossier_versions import fork_dossier
from .models import (
    FactDossier, OfficialResearchPage, OfficialResearchRequest,
    ProductionJob, SourceReference,
)
from .official_site_import import _parse_snapshot
from .official_site_preflight import plan_confirmed_official_source
from .official_site_research import research_official_website
from .safe_official_fetch import WebsiteFetchError


_RUN_LEASE = timedelta(seconds=80)
_RESEARCH_BUDGET_SECONDS = 60
_MAX_NEW_VERSIONS_PER_MINUTE = 10
_BLOCK_CODES = frozenset({
    "robots_unusable", "robots_disallowed", "crawl_delay_too_long",
    "unsafe_url", "unsafe_address", "dns_error", "redirect_blocked",
    "access_restricted", "http_error", "wrong_content_type",
    "encoded_response", "invalid_content_length", "response_too_large",
    "invalid_encoding",
})
_FAILURE_CODES = frozenset({
    "network_error", "research_deadline", "research_cancelled",
    "worker_lease_expired", "stale_dossier", "source_changed",
    "version_rate_limited", "invalid_snapshot", "worker_error",
})


class ResearchRunRejected(Exception):
    """Permit cannot be claimed. No external request was made."""


def _latest(job):
    return FactDossier.objects.filter(job=job).order_by("-version").first()


def _source_matches(row, latest):
    """Check *live* source and manual provenance against frozen consent."""
    if latest is None or latest.version != row.expected_version:
        return False
    source = SourceReference.objects.filter(
        pk=row.source_id, dossier=latest,
    ).select_related("dossier__job", "manual_confirmation").first()
    if source is None or row.job.owner_id != row.requested_by_id:
        return False
    plan = plan_confirmed_official_source(
        source, owner_id=row.requested_by_id, current_dossier_id=latest.pk,
    )
    return (
        plan is not None
        and plan.source_url == row.confirmed_url
        and plan.domain == row.confirmed_domain
        and plan.context == row.context
        and row.domain_rechecked is True
        and row.terms_rechecked is True
        and row.one_time_approved is True
        and row.max_pages == 4
    )


def _claim(*, owner_id, job_id, request_id):
    """Consume consent atomically; only this function may grant a network permit."""
    with transaction.atomic():
        job = ProductionJob.objects.select_for_update().filter(
            pk=job_id, owner_id=owner_id,
        ).first()
        if job is None:
            raise ResearchRunRejected("not_authorized")
        row = OfficialResearchRequest.objects.filter(
            pk=request_id, job=job, requested_by_id=owner_id,
        ).select_related("job").first()
        if row is None:
            raise ResearchRunRejected("not_authorized")
        now = timezone.now()
        if row.status == OfficialResearchRequest.Status.RUNNING:
            if row.lease_expires_at and row.lease_expires_at <= now:
                # Crash recovery is a terminal failure, NEVER a second try.
                OfficialResearchRequest.objects.filter(pk=row.pk).update(
                    status=OfficialResearchRequest.Status.FAILED,
                    finished_at=now, failure_code="worker_lease_expired",
                    lease_key=None,
                )
                return ("rejected", "already_consumed")
            raise ResearchRunRejected("already_consumed")
        if row.status != OfficialResearchRequest.Status.PENDING or row.attempt_count:
            raise ResearchRunRejected("already_consumed")
        if now >= row.expires_at:
            OfficialResearchRequest.objects.filter(pk=row.pk).update(
                status=OfficialResearchRequest.Status.EXPIRED,
                finished_at=now,
            )
            return ("rejected", "consent_expired")
        if not _source_matches(row, _latest(job)):
            OfficialResearchRequest.objects.filter(pk=row.pk).update(
                status=OfficialResearchRequest.Status.BLOCKED,
                finished_at=now, failure_code="source_changed",
            )
            return ("rejected", "source_changed")

        lease_key = uuid4()
        row.status = OfficialResearchRequest.Status.RUNNING
        row.attempt_count = 1
        row.lease_key = lease_key
        row.started_at = now
        row.lease_expires_at = now + _RUN_LEASE
        row.save(update_fields=[
            "status", "attempt_count", "lease_key",
            "started_at", "lease_expires_at",
        ])
        return (row.pk, lease_key, row.confirmed_url, row.context, now)


def _still_permitted(*, owner_id, job_id, request_id, token):
    """Before EVERY network request: check cancellation, lease, source, expiry.

    This is read-only and holds no DB lock during network I/O. A concurrent
    cancellation can stop the next fetch; the currently in-flight 5-second
    request may finish before the cooperative check notices cancellation.
    """
    row = OfficialResearchRequest.objects.filter(
        pk=request_id, job_id=job_id, requested_by_id=owner_id,
    ).select_related("job").first()
    now = timezone.now()
    if (
        row is None
        or row.status != OfficialResearchRequest.Status.RUNNING
        or row.lease_key != token
        or row.expires_at <= now
        or row.lease_expires_at is None
        or row.lease_expires_at <= now
        or not _source_matches(row, _latest(row.job))
    ):
        raise WebsiteFetchError("research_cancelled")


def _finish_failure(*, owner_id, job_id, request_id, token, code):
    """Never write an upstream exception or URL to owner-visible status."""
    status = (
        OfficialResearchRequest.Status.BLOCKED
        if code in _BLOCK_CODES else OfficialResearchRequest.Status.FAILED
    )
    safe_code = code if code in (_BLOCK_CODES | _FAILURE_CODES) else "worker_error"
    with transaction.atomic():
        job = ProductionJob.objects.select_for_update().filter(
            pk=job_id, owner_id=owner_id,
        ).first()
        if job is None:
            return False
        row = OfficialResearchRequest.objects.filter(
            pk=request_id, job=job, requested_by_id=owner_id,
        ).first()
        if (
            row is None or row.status != OfficialResearchRequest.Status.RUNNING
            or row.lease_key != token
        ):
            return False
        OfficialResearchRequest.objects.filter(pk=row.pk).update(
            status=status, finished_at=timezone.now(),
            failure_code=safe_code, lease_key=None,
        )
        return True


def _finish_success(*, owner_id, job_id, request_id, token,
                    snapshot, started_at):
    """Commit all source/page metadata and success in one transaction."""
    with transaction.atomic():
        job = ProductionJob.objects.select_for_update().filter(
            pk=job_id, owner_id=owner_id,
        ).select_related("club__league").first()
        if job is None:
            raise WebsiteFetchError("research_cancelled")
        row = OfficialResearchRequest.objects.filter(
            pk=request_id, job=job, requested_by_id=owner_id,
        ).first()
        if (
            row is None
            or row.status != OfficialResearchRequest.Status.RUNNING
            or row.lease_key != token
            or row.lease_expires_at is None
            or row.lease_expires_at <= timezone.now()
            or row.expires_at <= timezone.now()
        ):
            raise WebsiteFetchError("research_cancelled")
        previous = _latest(job)
        if previous is None or previous.version != row.expected_version:
            raise WebsiteFetchError("stale_dossier")
        if not _source_matches(row, previous):
            raise WebsiteFetchError("source_changed")
        if FactDossier.objects.filter(
            job=job,
            created_at__gte=timezone.now() - timedelta(minutes=1),
        ).count() >= _MAX_NEW_VERSIONS_PER_MINUTE:
            raise WebsiteFetchError("version_rate_limited")

        # Validate the existing guarded research output BEFORE allocating
        # any new dossier rows. The parser also rejects other hosts, >4
        # pages, missing category and unverified-status mismatches.
        parsed = _parse_snapshot(
            snapshot, job=job, homepage=row.confirmed_url,
            context=row.context, started_at=started_at,
        )
        if len(parsed) > row.max_pages:
            raise WebsiteFetchError("invalid_snapshot")

        dossier = fork_dossier(job=job, previous=previous)
        sources = {source.url: source for source in dossier.sources.all()}
        expected_kind = (
            SourceReference.Kind.CLUB_OFFICIAL if row.context == "club"
            else SourceReference.Kind.LEAGUE_OFFICIAL
        )
        saved = []
        for index, page in enumerate(parsed):
            existing = sources.get(page["url"])
            if existing is not None and existing.source_kind != expected_kind:
                raise WebsiteFetchError("invalid_snapshot")
            if existing is None:
                existing = SourceReference(
                    dossier=dossier, url=page["url"],
                    title=page["title"][:160], source_kind=expected_kind,
                    retrieved_at=page["retrieved_at"],
                    access_state=SourceReference.Access.ACCESSIBLE,
                )
                existing.full_clean()
                existing.save()
                sources[page["url"]] = existing
            saved.append(existing)

        # Page rows are only valid with SUCCEEDED request, and all mutations
        # below remain in this same transaction. Any failure rolls back
        # dossier+sources+state+pages together.
        row.status = OfficialResearchRequest.Status.SUCCEEDED
        row.finished_at = timezone.now()
        row.lease_key = None
        row.result_count = len(parsed)
        row.result_dossier_version = dossier.version
        row.save(update_fields=[
            "status", "finished_at", "lease_key",
            "result_count", "result_dossier_version",
        ])
        for index, (page, src) in enumerate(zip(parsed, saved)):
            raw = snapshot["pages"][index]
            OfficialResearchPage.objects.create(
                request=row, saved_source=src, position=index,
                url=page["url"], title=page["title"][:160],
                headings=raw["headings"], category=raw.get("category", ""),
                retrieved_at=page["retrieved_at"],
                verification_state="unverified",
            )
        return dossier.version


def execute_one_time_research(*, owner_id, job_id, request_id):
    """Run ONE explicitly selected request; no scheduler or automatic retry."""
    if any(type(v) is not int or v <= 0 for v in (owner_id, job_id, request_id)):
        raise ResearchRunRejected("not_authorized")
    claim = _claim(
        owner_id=owner_id, job_id=job_id, request_id=request_id,
    )
    # Marking an expired/stale/crashed request is committed before rejection.
    if claim[0] == "rejected":
        raise ResearchRunRejected(claim[1])
    pk, token, url, context, started_at = claim
    deadline = time.monotonic() + _RESEARCH_BUDGET_SECONDS

    def checkpoint():
        _still_permitted(
            owner_id=owner_id, job_id=job_id, request_id=pk, token=token,
        )

    try:
        # Only the worker service calls the existing vetted site adapter.
        from django.contrib.auth import get_user_model
        owner = get_user_model().objects.get(pk=owner_id)
        snapshot = research_official_website(
            owner=owner, job_id=job_id, homepage_url=url, context=context,
            identity_confirmed=True, terms_confirmed=True,
            deadline=deadline, continue_check=checkpoint,
        )
        checkpoint()
        if time.monotonic() >= deadline:
            raise WebsiteFetchError("research_deadline")
        return {
            "status": "succeeded",
            "request_id": pk,
            "dossier_version": _finish_success(
                owner_id=owner_id, job_id=job_id, request_id=pk,
                token=token, snapshot=snapshot, started_at=started_at,
            ),
        }
    except WebsiteFetchError as exc:
        _finish_failure(
            owner_id=owner_id, job_id=job_id, request_id=pk,
            token=token, code=exc.code,
        )
        return {"status": "stopped", "request_id": pk, "code": exc.code}
    except Exception:
        _finish_failure(
            owner_id=owner_id, job_id=job_id, request_id=pk,
            token=token, code="worker_error",
        )
        # Do not leak details to command output or owner-facing HTML.
        return {"status": "stopped", "request_id": pk, "code": "worker_error"}
