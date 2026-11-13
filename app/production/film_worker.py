"""FS-017: durable free-research worker for queued FILM jobs.

A PostgreSQL-backed ProductionJob is the queue. No browser needs to remain
open. One worker claims a queued job via SELECT ... FOR UPDATE; each stage
commits its own immutable dossier. On restart, stale RUNNING jobs can be
requeued after a generous inactivity threshold.

This milestone deliberately stops without an MP4: it cannot silently claim
that the not-yet-implemented licensed-media, TTS or FFmpeg pipeline ran.
"""
from datetime import timedelta
from importlib import import_module
import logging

from django.db import transaction
from django.utils import timezone

from .models import FactDossier, ProductionJob
from .research_autopilot import _IMPORTERS, research_plan
from .wikimedia_auto import AutoResearchError

logger = logging.getLogger(__name__)

_STAGES = ("club", "stadium", "players", "sources", "legends", "honours")
_MAX_STAGE_ATTEMPTS = 6
_STALE_AFTER = timedelta(minutes=60)
_NO_RENDERER = (
    "Die automatische Recherche wurde soweit möglich ausgeführt. "
    "Ein fertiges Video ist noch nicht verfügbar: der eigenständige "
    "Skript-, Sprach-, Medien- und MP4-Renderer befindet sich im Aufbau. "
    "Quellen und Recherche lassen sich optional bearbeiten."
)
_NO_CLUB = (
    "Die Vereinszuordnung konnte mit den freien Quellen nicht eindeutig "
    "recherchiert werden. Es wurde kein unbelegtes Video erstellt."
)
_UPSTREAM_FAILED = (
    "Die automatische Recherche konnte vorerst nicht abgeschlossen werden. "
    "Bisherige Dossierversionen bleiben gespeichert; es wurde kein Video erstellt."
)


def claim_queued_film_job():
    """Atomically claim exactly one queued FILM job, never a prototype."""
    with transaction.atomic():
        job = (
            ProductionJob.objects.select_for_update(skip_locked=True)
            .filter(kind=ProductionJob.Kind.FILM, status=ProductionJob.Status.QUEUED)
            .order_by("created_at", "pk")
            .first()
        )
        if job is None:
            return None
        job.transition_to(ProductionJob.Status.RUNNING)
        return job.pk


def recover_stale_film_jobs(*, now=None):
    """Recover only long-inactive film jobs; do not reclaim active workers.

    This relies on exactly one worker service in compose. The >=60 minute
    threshold exceeds the existing HTTP timeouts and bounded research steps.
    This is a recovery aid, not a distributed/externally fenced lease.
    """
    now = now or timezone.now()
    cutoff = now - _STALE_AFTER
    recovered = 0
    with transaction.atomic():
        stale = list(
            ProductionJob.objects.select_for_update(skip_locked=True)
            .filter(
                kind=ProductionJob.Kind.FILM,
                status=ProductionJob.Status.RUNNING,
                updated_at__lt=cutoff,
            ).order_by("pk")[:20]
        )
        for job in stale:
            job.transition_to(
                ProductionJob.Status.FAILED,
                error_message="Unterbrochener Produktionslauf wird erneut gestartet.",
            )
            job.transition_to(ProductionJob.Status.QUEUED)
            recovered += 1
    return recovered


def _heartbeat(job_id):
    ProductionJob.objects.filter(
        pk=job_id, kind=ProductionJob.Kind.FILM,
        status=ProductionJob.Status.RUNNING,
    ).update(updated_at=timezone.now())


def _finish_failed(job_id, message):
    with transaction.atomic():
        job = ProductionJob.objects.select_for_update().get(
            pk=job_id, kind=ProductionJob.Kind.FILM,
        )
        if job.status == ProductionJob.Status.RUNNING:
            job.transition_to(
                ProductionJob.Status.FAILED, error_message=message,
            )


def perform_film_research(job_id):
    """Work without browser interaction, skipping optional unavailable sites.

    At this stage there is intentionally NO automatic rendering. The run
    ends with a transparent not-rendered status even after research succeeds.
    Individual importers retain ownership, version and HTTPS/robots gates.
    """
    job = ProductionJob.objects.select_related("owner").get(
        pk=job_id, kind=ProductionJob.Kind.FILM,
        status=ProductionJob.Status.RUNNING,
    )
    try:
        for stage in _STAGES:
            latest = FactDossier.objects.filter(job=job).order_by("-version").first()
            plan = research_plan(job=job, dossier=latest)
            state = next(item["status"] for item in plan["steps"] if item["id"] == stage)
            # The interactive planner originally waited for P54 players
            # before P856 source discovery. For one-click production, P856
            # is independently useful even if the optional player scan
            # yielded no candidates.
            if (
                stage == "sources" and state == "waiting"
                and plan["steps"][0]["status"] == "completed"
            ):
                state = "ready"
            if state in ("completed", "requires_source", "waiting"):
                continue

            assert state == "ready", "Unknown research plan state."
            module_name, function_name = _IMPORTERS[stage]
            importer = getattr(
                import_module("app.production." + module_name), function_name,
            )
            expected_version = latest.version if latest is not None else 0
            try:
                importer(
                    owner=job.owner, job_id=job.pk,
                    expected_version=expected_version,
                )
            except AutoResearchError as exc:
                if stage == "club":
                    _finish_failed(job_id, _NO_CLUB)
                    return
                # Missing stadium, players, sources or official HTML must not
                # demand that the user click five different fallback forms.
                # We simply skip the optional enrichment on this job run.
                logger.info(
                    "Optional free research stage skipped: job_id=%s stage=%s code=%s",
                    job_id, stage, exc.code,
                )
            finally:
                _heartbeat(job_id)

        _finish_failed(job_id, _NO_RENDERER)
    except Exception:
        logger.exception("Film research worker failed: job_id=%s", job_id)
        _finish_failed(job_id, _UPSTREAM_FAILED)


def run_film_worker_once():
    """Process at most one queued film job; returns the claimed job ID."""
    job_id = claim_queued_film_job()
    if job_id is not None:
        perform_film_research(job_id)
    return job_id
