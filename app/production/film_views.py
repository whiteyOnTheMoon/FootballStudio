"""FS-017: first real, durable film job endpoint and owner-only status page.

A queued film job is NOT a rendered video. The worker can currently gather
free research but has no licensed-media/TTS/FFmpeg renderer; the UI says so.
No source confirmations, human FactReviews or paid API authorizations are
fabricated. All rendering capabilities remain disabled until implemented.
"""
from django import forms
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from app.clubs.models import Club
from .models import FactDossier, ProductionJob
from .research_autopilot import research_plan
from .dossiers import load_fact_dossier
from .film_claim_assessment import assess_research_snapshot


class FilmRequestForm(forms.Form):
    country = forms.CharField(min_length=2, max_length=3)
    league = forms.IntegerField(min_value=1)
    club = forms.IntegerField(min_value=1)


def _film_status(job):
    latest = FactDossier.objects.filter(job=job).order_by("-version").first()
    plan = research_plan(job=job, dossier=latest)
    assessment = None
    if latest is not None:
        snapshot = load_fact_dossier(
            owner=job.owner, job_id=job.pk, version=latest.version,
        )
        assessment = assess_research_snapshot(snapshot)
    return {
        "id": job.pk,
        "club": job.club_name,
        "title": job.title,
        "status": job.status,
        "dossier_version": plan["version"],
        "research_completed": plan["completed"],
        "research_total": plan["total"],
        "research_steps": plan["steps"],
        "machine_source_assessment": assessment,
        "video_ready": job.status == ProductionJob.Status.COMPLETED
        and bool(job.output_path),
        "message": job.error_message if job.status == ProductionJob.Status.FAILED
        else "Auftrag gespeichert. Der automatische Recherche-Worker startet."
        if job.status == ProductionJob.Status.QUEUED
        else "Automatische Recherche läuft. Die Seite darf geschlossen werden."
        if job.status == ProductionJob.Status.RUNNING
        else "Video fertig."
        if job.status == ProductionJob.Status.COMPLETED
        else "Produktionsauftrag angelegt.",
        "phase": (
            "queued" if job.status == ProductionJob.Status.QUEUED
            else "research" if job.status == ProductionJob.Status.RUNNING
            else "needs_pipeline" if job.status == ProductionJob.Status.FAILED
            else "completed" if job.status == ProductionJob.Status.COMPLETED
            else "draft"
        ),
    }


@login_required
@require_POST
@never_cache
def create_film_request(request):
    """One club selection, one click; no mandatory title/source/review fields."""
    form = FilmRequestForm(request.POST)
    if not form.is_valid():
        return JsonResponse({
            "error": "Bitte einen gültigen Verein über Land und Liga auswählen."
        }, status=400)
    data = form.cleaned_data
    club = get_object_or_404(
        Club.objects.select_related("league__country"),
        pk=data["club"], is_active=True,
        league_id=data["league"], league__is_active=True,
        league__country__code=data["country"],
        league__country__is_active=True,
    )
    with transaction.atomic():
        # The user row serializes simultaneous duplicate starts, including
        # concurrent requests handled by separate gunicorn workers.
        get_object_or_404(
            request.user.__class__.objects.select_for_update(),
            pk=request.user.pk,
        )
        active = ProductionJob.objects.filter(
            owner=request.user,
            club=club,
            kind=ProductionJob.Kind.FILM,
            status__in=(ProductionJob.Status.QUEUED, ProductionJob.Status.RUNNING),
        ).order_by("-pk").first()
        if active is not None:
            return JsonResponse({"job": _film_status(active), "created": False}, status=200)

        job = ProductionJob(
            owner=request.user,
            club=club,
            club_name=club.name,
            league_name=club.league.name,
            country_code=club.league.country.code,
            title=("The Story of " + club.name)[:180],
            language="en",
            kind=ProductionJob.Kind.FILM,
            status=ProductionJob.Status.QUEUED,
        )
        job.full_clean()
        job.save()
    return JsonResponse({"job": _film_status(job), "created": True}, status=201)


@login_required
@require_GET
@never_cache
def film_status_json(request, job_id):
    job = get_object_or_404(
        ProductionJob, pk=job_id, owner=request.user,
        kind=ProductionJob.Kind.FILM,
    )
    return JsonResponse({"job": _film_status(job)})


@login_required
@require_GET
@never_cache
def film_status_page(request, job_id):
    job = get_object_or_404(
        ProductionJob, pk=job_id, owner=request.user,
        kind=ProductionJob.Kind.FILM,
    )
    return render(request, "studio/film_status.html", {
        "job": job,
        "film": _film_status(job),
    })
