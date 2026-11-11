"""Read-only, owner-scoped M2 preview of deterministic English script units.

This does NOT create or publish an actual documentary script or start a job.
The review-enforced standalone helper cannot fetch sites, render media or
invoke an LLM. Only the already private dossier reader touches the DB.
"""
import re

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .dossiers import load_fact_dossier
from .models import FactDossier, ProductionJob
from .script_safety import prepare_script_preview


@login_required
@require_GET
@never_cache
def safe_script_preview(request, job_id):
    job = get_object_or_404(ProductionJob, pk=job_id, owner=request.user)
    latest = FactDossier.objects.filter(job=job).order_by("-version").first()
    if latest is None:
        raise Http404("No research dossier.")
    raw_version = request.GET.get("version")
    if raw_version is None:
        version = latest.version
    elif re.fullmatch(r"[1-9][0-9]{0,8}", raw_version):
        version = int(raw_version)
    else:
        raise Http404("Unknown dossier version.")

    try:
        snapshot = load_fact_dossier(
            owner=request.user, job_id=job.pk, version=version,
        )
    except FactDossier.DoesNotExist:
        raise Http404("Unknown dossier version.") from None

    preview = prepare_script_preview(snapshot)
    counts = {
        state: sum(unit["disposition"] == state for unit in preview["units"])
        for state in ("usable", "caution", "conflicted", "omit")
    }
    return render(request, "studio/safe_script_preview.html", {
        "job": job,
        "version": version,
        "latest_version": latest.version,
        "units": preview["units"],
        "counts": counts,
    })
