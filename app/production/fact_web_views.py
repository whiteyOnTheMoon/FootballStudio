"""Owner-only HTML UI for *manual* unverified, source-bound fact proposals.

No user-provided URL is fetched or turned into a trusted SourceReference.
Every POST is CSRF-protected by Django middleware; the internal proposal
service still enforces atomic owner, dossier version and source-ID checks.
"""
from datetime import timedelta
import re

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .fact_proposals import propose_official_fact
from .fact_web_forms import ManualFactProposalForm
from .models import FactDossier, ProductionJob, SourceReference


# Bound by database-backed dossier versions, not per-process in-memory cache.
# The same limit applies across multiple Gunicorn workers under PostgreSQL.
_MAX_NEW_DOSSIERS_PER_MINUTE = 10
_VALID_VERSION = re.compile(r"[1-9][0-9]{0,8}\Z")


def _official_sources(dossier):
    if dossier is None:
        return SourceReference.objects.none()
    return dossier.sources.filter(
        source_kind__in=(
            SourceReference.Kind.CLUB_OFFICIAL,
            SourceReference.Kind.LEAGUE_OFFICIAL,
        ),
        access_state=SourceReference.Access.ACCESSIBLE,
    ).order_by("pk")


def _display(request, *, job, latest, form, status=200, error_message=""):
    return render(request, "studio/fact_proposal.html", {
        "job": job,
        "current_version": latest.version if latest else None,
        "form": form,
        "has_eligible_sources": _official_sources(latest).exists(),
        "error_message": error_message,
    }, status=status)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def manual_fact_proposal(request, job_id):
    job = get_object_or_404(ProductionJob, pk=job_id, owner=request.user)
    latest = FactDossier.objects.filter(job=job).order_by("-version").first()

    if request.method == "GET":
        form = ManualFactProposalForm(
            sources=_official_sources(latest),
            initial_version=latest.version if latest else None,
        )
        return _display(request, job=job, latest=latest, form=form)

    posted_version = request.POST.get("expected_version", "")
    if not _VALID_VERSION.fullmatch(posted_version):
        form = ManualFactProposalForm(
            request.POST, sources=SourceReference.objects.none(),
        )
        form.is_valid()
        return _display(
            request, job=job, latest=latest, form=form, status=400,
            error_message="Ungültige Dossierversion. Bitte Formular neu laden.",
        )

    # A retry of the exact same submission is accepted by the internal
    # service even if the latest dossier has advanced. An unrelated stale
    # submission is rejected with 409; the old owner-scoped source ID never
    # gives access to another user's dossier.
    requested = FactDossier.objects.filter(
        job=job, version=int(posted_version),
    ).first()
    sources = _official_sources(requested)
    form = ManualFactProposalForm(request.POST, sources=sources)
    if not form.is_valid():
        return _display(
            request, job=job, latest=latest, form=form, status=400,
            error_message="Bitte die markierten Felder und die Quellenzuordnung prüfen.",
        )

    payload = form.cleaned_data
    try:
        with transaction.atomic():
            locked_job = ProductionJob.objects.select_for_update().get(
                pk=job.pk, owner=request.user,
            )
            latest_locked = FactDossier.objects.filter(
                job=locked_job,
            ).order_by("-version").first()
            if (
                latest_locked is not None
                and latest_locked.version == payload["expected_version"]
                and FactDossier.objects.filter(
                    job=locked_job,
                    created_at__gte=timezone.now() - timedelta(minutes=1),
                ).count() >= _MAX_NEW_DOSSIERS_PER_MINUTE
            ):
                return _display(
                    request, job=job, latest=latest_locked, form=form, status=429,
                    error_message=(
                        "Zu viele Änderungen innerhalb einer Minute. "
                        "Bitte später erneut versuchen."
                    ),
                )

            dossier = propose_official_fact(
                owner=request.user,
                job_id=job.pk,
                expected_version=payload["expected_version"],
                source_id=payload["source"].pk,
                predicate=payload["predicate"],
                value=payload["fact_value"],
                assertion_text=payload["assertion_text"],
                locator=payload["locator"],
                evidence_summary=payload["evidence_summary"],
            )
    except ValueError as exc:
        # Never echo low-level model or database errors to the browser.
        if "Stale dossier version" in str(exc):
            return _display(
                request, job=job, latest=latest, form=form, status=409,
                error_message=(
                    "Das Dossier wurde inzwischen geändert. "
                    "Bitte zur aktuellen Rechercheansicht zurückkehren "
                    "und das Formular neu öffnen."
                ),
            )
        return _display(
            request, job=job, latest=latest, form=form, status=400,
            error_message="Der Faktenvorschlag ist ungültig. Angaben bitte prüfen.",
        )
    except (FactDossier.DoesNotExist, SourceReference.DoesNotExist):
        return _display(
            request, job=job, latest=latest, form=form, status=409,
            error_message=(
                "Die Quelle oder Dossierversion ist nicht mehr verfügbar. "
                "Bitte den neuesten Recherchestand öffnen."
            ),
        )

    return redirect(
        f"{reverse('research-job', kwargs={'job_id': job.pk})}"
        f"?version={dossier.version}#facts-heading"
    )
