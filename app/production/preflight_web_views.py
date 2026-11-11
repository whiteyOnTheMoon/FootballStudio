"""Owner-only read-only official-site preflight, with zero external effects.

The view intentionally accepts GET alone. A manual SourceConfirmation is
not a permission token to crawl; a later independent, CSRF-protected,
rate-limited job workflow must request consent again before any HTTP fetch.
"""
import re

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import FactDossier, ProductionJob, SourceReference
from .official_site_preflight import plan_confirmed_official_source


_VALID_SOURCE = re.compile(r"[1-9][0-9]{0,17}\Z")
_MAX_SELECTION_ITEMS = 100


@login_required
@require_GET
@never_cache
def official_research_preflight(request, job_id):
    job = get_object_or_404(ProductionJob, pk=job_id, owner=request.user)
    dossier = FactDossier.objects.filter(job=job).order_by("-version").first()
    if dossier is None:
        if request.GET.get("source_id") is not None:
            raise Http404("Unknown confirmed source.")
        return render(request, "studio/official_research_preflight.html", {
            "job": job,
            "dossier": None,
            "choices": (),
            "selected": None,
        })

    candidates = dossier.sources.filter(
        source_kind__in=(
            SourceReference.Kind.CLUB_OFFICIAL,
            SourceReference.Kind.LEAGUE_OFFICIAL,
        ),
        access_state=SourceReference.Access.ACCESSIBLE,
        manual_confirmation__isnull=False,
    ).select_related("dossier__job", "manual_confirmation").order_by("pk")

    choices = []
    for row in candidates[:_MAX_SELECTION_ITEMS]:
        approved = plan_confirmed_official_source(
            row, owner_id=request.user.pk, current_dossier_id=dossier.pk,
        )
        if approved is not None:
            choices.append(approved)

    source_id = request.GET.get("source_id")
    selected = None
    if source_id is not None:
        if (
            not isinstance(source_id, str)
            or not _VALID_SOURCE.fullmatch(source_id)
            or int(source_id) > 2**63 - 1
        ):
            raise Http404("Unknown confirmed source.")
        source = get_object_or_404(candidates, pk=int(source_id))
        selected = plan_confirmed_official_source(
            source, owner_id=request.user.pk, current_dossier_id=dossier.pk,
        )
        if selected is None:
            raise Http404("Unknown confirmed source.")

    return render(request, "studio/official_research_preflight.html", {
        "job": job,
        "dossier": dossier,
        "choices": choices,
        "selected": selected,
        "selection_limit": _MAX_SELECTION_ITEMS,
    })
