"""Owner-only human approval UI for *unexecuted* one-time research requests.

POST saves an expiring record under DB lock; it does not fetch robots.txt,
start a task, contact any URL or mark any fact verified.
"""
from uuid import uuid4

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import (
    FactDossier, OfficialResearchRequest, ProductionJob, SourceReference,
)
from .official_site_preflight import plan_confirmed_official_source
from .research_consent_forms import OneTimeResearchConsentForm
from .research_consents import (
    ResearchConsentConflict, ResearchConsentInvalid,
    ResearchConsentRateLimited, ResearchConsentStale,
    cancel_one_time_research_consent, record_one_time_research_consent,
)


def _source_for_job(job, source_id, owner):
    latest = FactDossier.objects.filter(job=job).order_by("-version").first()
    if latest is None:
        raise Http404("No current research dossier.")
    source = get_object_or_404(
        SourceReference.objects.select_related(
            "dossier__job", "manual_confirmation",
        ),
        pk=source_id, dossier=latest,
    )
    plan = plan_confirmed_official_source(
        source, owner_id=owner.pk, current_dossier_id=latest.pk,
    )
    if plan is None:
        raise Http404("Unknown confirmed official source.")
    return latest, plan


def _form_response(request, job, latest, plan, form, *, status=200, error=""):
    already = OfficialResearchRequest.objects.filter(
        job=job, status=OfficialResearchRequest.Status.PENDING,
    ).order_by("-consented_at").first()
    return render(request, "studio/research_consent.html", {
        "job": job,
        "dossier": latest,
        "source": plan,
        "form": form,
        "existing": already,
        "error_message": error,
    }, status=status)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def approve_one_time_research(request, job_id, source_id):
    job = get_object_or_404(ProductionJob, pk=job_id, owner=request.user)
    latest, plan = _source_for_job(job, source_id, request.user)

    if request.method == "GET":
        form = OneTimeResearchConsentForm(initial={
            "expected_version": latest.version,
            "request_key": uuid4(),
        })
        return _form_response(request, job, latest, plan, form)

    form = OneTimeResearchConsentForm(request.POST)
    if not form.is_valid():
        return _form_response(
            request, job, latest, plan, form, status=400,
            error="Bitte alle drei neuen Zustimmungen und die gültige Dossioversion prüfen.",
        )

    fields = form.cleaned_data
    try:
        approval, _created = record_one_time_research_consent(
            owner=request.user,
            job_id=job.pk, source_id=source_id,
            expected_version=fields["expected_version"],
            request_key=fields["request_key"],
            domain_rechecked=fields["domain_rechecked"],
            terms_rechecked=fields["terms_rechecked"],
            one_time_approved=fields["one_time_approved"],
        )
    except ResearchConsentStale:
        return _form_response(
            request, job, latest, plan, form, status=409,
            error="Das Dossier hat sich geändert. Bitte eine aktuelle Quelle erneut auswählen.",
        )
    except ResearchConsentConflict:
        return _form_response(
            request, job, latest, plan, form, status=409,
            error="Für diesen Job besteht bereits ein Auftrag oder diese Freigabe wurde schon verbraucht.",
        )
    except ResearchConsentRateLimited:
        return _form_response(
            request, job, latest, plan, form, status=429,
            error="Die tägliche Grenze für Recherchefreigaben ist erreicht. Es wurde kein Auftrag angelegt.",
        )
    except ResearchConsentInvalid:
        return _form_response(
            request, job, latest, plan, form, status=400,
            error="Die Freigabe konnte nicht übernommen werden. Bitte Daten und Zustimmungen prüfen.",
        )

    return redirect(
        f"{reverse('research-requests', kwargs={'job_id': job.pk})}"
        f"?request_id={approval.pk}"
    )


@login_required
@never_cache
def list_research_requests(request, job_id):
    # For all methods: enforce owner boundary *before* reporting 405.
    job = get_object_or_404(ProductionJob, pk=job_id, owner=request.user)
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    records = list(OfficialResearchRequest.objects.filter(
        job=job, requested_by=request.user,
    ).order_by("-consented_at", "-pk")[:30])
    return render(request, "studio/research_requests.html", {
        "job": job,
        "records": records,
    })


@login_required
@never_cache
@require_POST
def cancel_research_request(request, job_id, request_id):
    job = get_object_or_404(ProductionJob, pk=job_id, owner=request.user)
    try:
        cancel_one_time_research_consent(
            owner=request.user, job_id=job.pk, request_id=request_id,
        )
    except (ResearchConsentInvalid, OfficialResearchRequest.DoesNotExist):
        raise Http404("Unknown research request.") from None
    return redirect(reverse("research-requests", kwargs={"job_id": job.pk}))
