"""CSRF-protected owner-only HTML review of one existing fact's evidence.

No source URL input, DNS lookup, robots request, HTML fetch, LLM or video.
A supporting role is NOT verification. Reviewed facts become unverified
in the new snapshot whenever their evidence set changes.
"""
import re
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .evidence_web_forms import EvidenceReviewForm
from .fact_reviews import append_review_evidence
from .models import FactDossier, ProductionJob, SourceReference
from .views import _safe_source_link

_VALID_VERSION = re.compile(r"[1-9][0-9]{0,8}\Z")
_MAX_NEW_DOSSIERS_PER_MINUTE = 10


def _sources(dossier):
    """Existing accessible, syntactically safe, own-dossier sources only."""
    if dossier is None:
        return SourceReference.objects.none()
    accessible = dossier.sources.filter(
        access_state=SourceReference.Access.ACCESSIBLE,
    ).select_related("manual_confirmation").order_by("pk")
    eligible_ids = [
        source.pk for source in accessible
        if _safe_source_link(source.url) is not None
    ]
    return accessible.filter(pk__in=eligible_ids)


def _same_fact(old, new):
    return (
        old.predicate == new.predicate
        and old.value == new.value
        and old.assertion_text == new.assertion_text
    )


def _exact_retry_exists(*, base, latest, fact, source, fields):
    """Recognize only exact duplicate submissions across cloned snapshots.

    Fact/source PKs are version-specific. The fork operation preserves the
    ordering of existing facts. Require the same ordinal, exact predicate,
    value and assertion text, and a uniquely matching source fingerprint.
    Never accept a changed stale POST or a lookalike source from another job.
    """
    old_fact_ids = list(base.facts.order_by("pk").values_list("pk", flat=True))
    try:
        index = old_fact_ids.index(fact.pk)
    except ValueError:
        return False
    current_fact_ids = list(latest.facts.order_by("pk").values_list("pk", flat=True))
    if index >= len(current_fact_ids):
        return False
    current_fact = latest.facts.get(pk=current_fact_ids[index])
    if not _same_fact(fact, current_fact):
        return False
    matching = latest.sources.filter(
        url=source.url,
        source_kind=source.source_kind,
        retrieved_at=source.retrieved_at,
        access_state=SourceReference.Access.ACCESSIBLE,
    )
    if matching.count() != 1:
        return False
    return current_fact.evidence.filter(
        source=matching.get(),
        role=fields["role"],
        locator=fields["locator"],
        summary=fields["summary"],
    ).exists()


def _render_form(request, *, job, dossier, fact, form, status=200, error=""):
    available = list(_sources(dossier))
    display_sources = []
    for source in available:
        try:
            manual = source.manual_confirmation
        except Exception as exc:
            from .models import SourceConfirmation
            if not isinstance(exc, SourceConfirmation.DoesNotExist):
                raise
            manual = None
        display_sources.append({
            "id": source.pk,
            "title": source.title,
            "url": source.url,
            "safe_link": _safe_source_link(source.url),
            "source_kind": source.source_kind,
            "source_time": manual.checked_at if manual is not None else source.retrieved_at,
            "manual": manual is not None,
        })
    existing = []
    for item in fact.evidence.select_related("source").order_by("pk"):
        existing.append({
            "role": item.role,
            "locator": item.locator,
            "summary": item.summary,
            "source_title": item.source.title,
            "source_url": item.source.url,
            "safe_link": _safe_source_link(item.source.url),
        })
    return render(request, "studio/evidence_review.html", {
        "job": job,
        "dossier": dossier,
        "fact": fact,
        "form": form,
        "available_sources": display_sources,
        "existing_evidence": existing,
        "error_message": error,
    }, status=status)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def review_evidence(request, job_id, fact_id):
    job = get_object_or_404(ProductionJob, pk=job_id, owner=request.user)
    current = FactDossier.objects.filter(job=job).order_by("-version").first()
    if current is None:
        raise Http404("No research facts found.")

    if request.method == "GET":
        fact = get_object_or_404(current.facts, pk=fact_id)
        form = EvidenceReviewForm(
            sources=_sources(current), initial_version=current.version,
        )
        return _render_form(
            request, job=job, dossier=current, fact=fact, form=form,
        )

    raw_version = request.POST.get("expected_version", "")
    if not _VALID_VERSION.fullmatch(raw_version):
        # Never use a forged path fact ID to display an unrelated job's fact.
        fact = get_object_or_404(current.facts, pk=fact_id)
        form = EvidenceReviewForm(
            request.POST, sources=SourceReference.objects.none(),
        )
        form.is_valid()
        return _render_form(
            request, job=job, dossier=current, fact=fact, form=form,
            status=400, error="Ungültige Dossierversion. Bitte Formular neu laden.",
        )

    base = FactDossier.objects.filter(
        job=job, version=int(raw_version),
    ).first()
    if base is None:
        raise Http404("No such research version.")
    fact = get_object_or_404(base.facts, pk=fact_id)
    form = EvidenceReviewForm(request.POST, sources=_sources(base))
    if not form.is_valid():
        return _render_form(
            request, job=job, dossier=base, fact=fact, form=form,
            status=400, error="Bitte Quelle, Rolle, Fundstelle und Bestätigung prüfen.",
        )

    fields = form.cleaned_data
    with transaction.atomic():
        # Serialize with the other M2 writers across gunicorn/PostgreSQL.
        locked = ProductionJob.objects.select_for_update().get(
            pk=job.pk, owner=request.user,
        )
        latest = FactDossier.objects.filter(job=locked).order_by("-version").first()

        if latest.pk != base.pk:
            if _exact_retry_exists(
                base=base, latest=latest, fact=fact,
                source=fields["source"], fields=fields,
            ):
                return redirect(
                    f"{reverse('research-job', kwargs={'job_id': job.pk})}"
                    f"?version={latest.version}#facts-heading"
                )
            return _render_form(
                request, job=job, dossier=base, fact=fact, form=form,
                status=409, error=(
                    "Das Dossier wurde inzwischen geändert. Bitte die aktuelle "
                    "Faktenansicht öffnen und die Fundstelle erneut prüfen."
                ),
            )

        if (
            FactDossier.objects.filter(
                job=locked,
                created_at__gte=timezone.now() - timedelta(minutes=1),
            ).count() >= _MAX_NEW_DOSSIERS_PER_MINUTE
            and not fact.evidence.filter(
                source=fields["source"], role=fields["role"],
                locator=fields["locator"], summary=fields["summary"],
            ).exists()
        ):
            return _render_form(
                request, job=job, dossier=base, fact=fact, form=form,
                status=429, error=(
                    "Zu viele neue Recherchestände innerhalb einer Minute. "
                    "Bitte später erneut versuchen."
                ),
            )

        try:
            updated = append_review_evidence(
                owner=request.user,
                job_id=job.pk,
                expected_version=base.version,
                fact_id=fact.pk,
                source_id=fields["source"].pk,
                role=fields["role"],
                locator=fields["locator"],
                summary=fields["summary"],
                source_checked=fields["source_checked"],
            )
        except (ValueError, SourceReference.DoesNotExist) as exc:
            # A concurrent version update or invalidated source must not
            # disclose database internals or create new dossier data.
            conflict = "Stale dossier version" in str(exc)
            return _render_form(
                request, job=job, dossier=base, fact=fact, form=form,
                status=409 if conflict else 400,
                error=(
                    "Das Dossier wurde geändert. Bitte neu laden."
                    if conflict else "Der Beleg konnte nicht übernommen werden."
                ),
            )

    return redirect(
        f"{reverse('research-job', kwargs={'job_id': job.pk})}"
        f"?version={updated.version}#facts-heading"
    )
