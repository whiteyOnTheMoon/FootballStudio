"""Owner-protected, CSRF-checked manual official website source references.

Only writes a source URI and a human provenance record. No DNS, HTTP, robots
fetch, site content extraction, or automatic fact verification.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .manual_source_import import (
    ManualSourceConflict, ManualSourceRateLimited, ManualSourceStale,
    register_manual_official_source,
)
from .models import FactDossier, ProductionJob
from .source_web_forms import ManualOfficialSourceForm


def _response(request, *, job, latest, form, message="", status=200):
    return render(request, "studio/source_confirmation.html", {
        "job": job,
        "latest_version": latest.version if latest else 0,
        "form": form,
        "error_message": message,
    }, status=status)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def manual_official_source(request, job_id):
    # Check job ownership first, even for malformed POSTs.
    job = get_object_or_404(ProductionJob, pk=job_id, owner=request.user)
    latest = FactDossier.objects.filter(job=job).order_by("-version").first()

    if request.method == "GET":
        form = ManualOfficialSourceForm(
            initial_version=latest.version if latest else 0,
        )
        if request.GET.get("candidate") in ("club", "league"):
            from .official_source_candidates import proposed_site_for_context
            candidate = proposed_site_for_context(
                latest, request.GET["candidate"],
            )
            if candidate is not None:
                # Only URL, category and title are filled automatically.
                # The evidence assessment, basis and three required consent
                # checkboxes remain blank for an actual human decision.
                form.initial.update({
                    "context": candidate["context"],
                    "url": candidate["url"],
                    "title": candidate["title"],
                })
        return _response(request, job=job, latest=latest, form=form)

    # Request parameters are never used for a fetch. They undergo Django
    # form validation followed by the locked/owner-scoped service checks.
    form = ManualOfficialSourceForm(request.POST)
    if not form.is_valid():
        return _response(
            request, job=job, latest=latest, form=form, status=400,
            message="Bitte URL, Herkunftsangaben und alle drei Bestätigungen prüfen.",
        )

    fields = form.cleaned_data
    try:
        dossier = register_manual_official_source(
            owner=request.user,
            job_id=job.pk,
            expected_version=fields["expected_version"],
            url=fields["url"],
            title=fields["title"],
            context=fields["context"],
            basis=fields["basis"],
            identity_confirmed=fields["identity_confirmed"],
            terms_confirmed=fields["terms_confirmed"],
            access_confirmed=fields["access_confirmed"],
        )
    except ManualSourceRateLimited:
        return _response(
            request, job=job, latest=latest, form=form, status=429,
            message="Zu viele neue Recherchestände innerhalb einer Minute. Bitte später erneut versuchen.",
        )
    except ManualSourceStale:
        return _response(
            request, job=job, latest=latest, form=form, status=409,
            message="Das Dossier wurde inzwischen geändert. Bitte das Formular neu öffnen.",
        )
    except ManualSourceConflict:
        return _response(
            request, job=job, latest=latest, form=form, status=409,
            message=(
                "Diese Adresse ist bereits mit anderer Herkunft, Kategorie oder "
                "anderen Angaben gespeichert. Es wurde nichts überschrieben."
            ),
        )
    except ValueError:
        return _response(
            request, job=job, latest=latest, form=form, status=400,
            message="Die Quelle konnte nicht übernommen werden. Bitte die Angaben prüfen.",
        )

    return redirect(
        f"{reverse('research-job', kwargs={'job_id': job.pk})}"
        f"?version={dossier.version}#sources-heading"
    )
