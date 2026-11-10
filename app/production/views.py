"""Authenticated and owner-scoped M1 selection test jobs.

No worker is triggered and no external API is called. This deliberately
tests database persistence and the selected club's parent relationships.
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from app.clubs.models import Club

from .forms import TestJobForm
from .models import ProductionJob


def as_public_data(job):
    return {
        "id": job.pk,
        "title": job.title,
        "language": job.language,
        "kind": job.kind,
        "status": job.status,
        "country_code": job.country_code,
        "league": job.league_name,
        "club": job.club_name,
        "club_id": job.club_id,
        "error": job.error_message,
        "has_video": bool(job.output_path),
        "created_at": job.created_at.isoformat(),
    }


@login_required
@require_GET
@never_cache
def test_job_list(request):
    jobs = ProductionJob.objects.filter(owner=request.user)[:20]
    return JsonResponse({"jobs": [as_public_data(job) for job in jobs]})


@login_required
@require_POST
@never_cache
def create_test_job(request):
    form = TestJobForm(request.POST)
    if not form.is_valid():
        return JsonResponse({
            "error": "Select a valid country, league and club, and enter a title of at least four characters."
        }, status=400)
    payload = form.cleaned_data
    club = get_object_or_404(
        Club.objects.select_related("league__country"),
        pk=payload["club"], is_active=True,
        league_id=payload["league"], league__is_active=True,
        league__country__code=payload["country"],
        league__country__is_active=True,
    )
    job = ProductionJob(
        owner=request.user,
        club=club,
        title=payload["title"],
        language="en",
        kind=ProductionJob.Kind.PROTOTYPE,
        status=ProductionJob.Status.QUEUED,
        country_code=club.league.country.code,
        league_name=club.league.name,
        club_name=club.name,
    )
    job.full_clean()
    job.save()
    return JsonResponse({
        "job": as_public_data(job),
        "notice": "M1 selection test saved. Video generation is not active yet.",
    }, status=201)
