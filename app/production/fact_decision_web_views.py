"""Explicit human fact decisions in an owner-scoped browser form.

Only the authorized job owner can view or decide a fact in the current
dossier. A status change requires the existing reviewed-evidence service,
a meaningful note and explicit confirmations; no external requests run.
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

from .fact_decision_web_forms import HumanFactDecisionForm
from .fact_reviews import decide_fact_review
from .models import FactDossier, FactReview, ProductionJob, SourceConfirmation
from .views import _safe_source_link


_VALID_VERSION = re.compile(r"[1-9][0-9]{0,8}\Z")
_MAX_NEW_DOSSIERS_PER_MINUTE = 10


def _evidence_fingerprint(fact):
    """Compare review prerequisites across cloned dossier versions."""
    return sorted((
        item.source.url, item.source.source_kind,
        item.source.retrieved_at.isoformat(), item.source.access_state,
        item.role, item.locator, item.summary,
    ) for item in fact.evidence.select_related("source"))


def _same_fact(old, new):
    return (
        old.predicate == new.predicate
        and old.value == new.value
        and old.assertion_text == new.assertion_text
        and _evidence_fingerprint(old) == _evidence_fingerprint(new)
    )


def _decision_exists(fact, fields, owner_id):
    try:
        review = fact.review
    except FactReview.DoesNotExist:
        return False
    return (
        review.reviewer_id == owner_id
        and review.decision == fields["decision"]
        and review.note == fields["review_note"]
        and review.checked_source == fields["source_checked"]
        and review.checked_season == fields["season_checked"]
        and fact.verification_state == fields["decision"]
    )


def _exact_retry(*, base, latest, fact, fields, owner_id):
    """Accept just the immediately following unchanged snapshot's same review.

    Old fact IDs cannot be used to review newer facts: this is solely an
    idempotent retry after a successful POST and one consecutive fork.
    """
    if latest.version != base.version + 1:
        return False
    previous_ids = list(base.facts.order_by("pk").values_list("pk", flat=True))
    newest_ids = list(latest.facts.order_by("pk").values_list("pk", flat=True))
    try:
        position = previous_ids.index(fact.pk)
    except ValueError:
        return False
    if len(previous_ids) != len(newest_ids):
        return False
    candidate = latest.facts.get(pk=newest_ids[position])
    return (
        _same_fact(fact, candidate)
        and _decision_exists(candidate, fields, owner_id)
    )


def _review_problem(exc):
    """User-facing review explanation, without database internals."""
    message = str(exc)
    if "Unresolved contradictory" in message:
        return "Ungeklärte Gegenbelege verhindern eine Verifikation."
    if "supporting AND contradicting" in message:
        return "Für „widersprüchlich“ sind geprüfte stützende und widersprechende Fundstellen nötig."
    if "supporting locator" in message:
        return "„Verifiziert“ verlangt eine selbst geprüfte zugängliche stützende Fundstelle."
    if "specific season" in message or "season cross-check" in message:
        return "Die behauptete Saison muss in jeder stützenden Fundstelle übereinstimmen und geprüft sein."
    if "Unresolved contradictions must" in message:
        return "Ungeklärte Gegenbelege müssen als Widerspruch oder verworfener Fakt behandelt werden."
    return "Diese Entscheidung ist mit den vorhandenen Belegen nicht zulässig."


def _render(request, *, job, dossier, fact, form, status=200, error=""):
    items = []
    has_support, has_contradiction = False, False
    for evidence in fact.evidence.select_related(
        "source", "source__manual_confirmation"
    ).order_by("pk"):
        source = evidence.source
        try:
            manual = source.manual_confirmation
        except SourceConfirmation.DoesNotExist:
            manual = None
        if evidence.role == "supports":
            has_support = True
        elif evidence.role == "contradicts":
            has_contradiction = True
        items.append({
            "role": evidence.role,
            "locator": evidence.locator,
            "summary": evidence.summary,
            "source_id": source.pk,
            "source_title": source.title,
            "source_url": source.url,
            "source_kind": source.source_kind,
            "access_state": source.access_state,
            "safe_link": _safe_source_link(source.url),
            "time": manual.checked_at if manual is not None else source.retrieved_at,
            "manual": manual is not None,
        })
    try:
        old_review = fact.review
    except FactReview.DoesNotExist:
        old_review = None
    return render(request, "studio/fact_decision.html", {
        "job": job,
        "dossier": dossier,
        "fact": fact,
        "form": form,
        "evidence_items": items,
        "has_contradiction": has_contradiction,
        "has_support": has_support,
        "old_review": old_review,
        "is_seasonal": form.is_seasonal,
        "error_message": error,
    }, status=status)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def decide_fact_in_browser(request, job_id, fact_id):
    job = get_object_or_404(ProductionJob, pk=job_id, owner=request.user)
    latest = FactDossier.objects.filter(job=job).order_by("-version").first()
    if latest is None:
        raise Http404("No facts have been researched.")

    if request.method == "GET":
        fact = get_object_or_404(latest.facts, pk=fact_id)
        form = HumanFactDecisionForm(fact=fact, initial_version=latest.version)
        return _render(request, job=job, dossier=latest, fact=fact, form=form)

    version_text = request.POST.get("expected_version", "")
    if not _VALID_VERSION.fullmatch(version_text):
        fact = get_object_or_404(latest.facts, pk=fact_id)
        form = HumanFactDecisionForm(request.POST, fact=fact)
        form.is_valid()
        return _render(
            request, job=job, dossier=latest, fact=fact, form=form,
            status=400, error="Ungültige Dossierversion. Bitte das Formular neu öffnen.",
        )

    base = FactDossier.objects.filter(
        job=job, version=int(version_text),
    ).first()
    if base is None:
        raise Http404("Unknown dossier version.")
    fact = get_object_or_404(base.facts, pk=fact_id)
    form = HumanFactDecisionForm(request.POST, fact=fact)
    if not form.is_valid():
        return _render(
            request, job=job, dossier=base, fact=fact, form=form,
            status=400, error="Bitte Entscheidung, Begründung und Prüfbestätigungen ergänzen.",
        )
    fields = form.cleaned_data

    with transaction.atomic():
        locked_job = ProductionJob.objects.select_for_update().get(
            pk=job.pk, owner=request.user,
        )
        current = FactDossier.objects.filter(
            job=locked_job,
        ).order_by("-version").first()
        if current.pk != base.pk:
            if _exact_retry(
                base=base, latest=current, fact=fact,
                fields=fields, owner_id=request.user.pk,
            ):
                return redirect(
                    f"{reverse('research-job', kwargs={'job_id': job.pk})}"
                    f"?version={current.version}#facts-heading"
                )
            return _render(
                request, job=job, dossier=base, fact=fact, form=form,
                status=409,
                error=(
                    "Das Dossier wurde inzwischen geändert. Bitte den aktuellen "
                    "Fakt öffnen und alle Belege erneut prüfen."
                ),
            )

        if (
            not _decision_exists(fact, fields, request.user.pk)
            and FactDossier.objects.filter(
                job=locked_job,
                created_at__gte=timezone.now() - timedelta(minutes=1),
            ).count() >= _MAX_NEW_DOSSIERS_PER_MINUTE
        ):
            return _render(
                request, job=job, dossier=base, fact=fact, form=form,
                status=429,
                error="Zu viele neue Recherchestände innerhalb einer Minute. Bitte später erneut versuchen.",
            )

        try:
            updated = decide_fact_review(
                owner=request.user,
                job_id=job.pk,
                expected_version=base.version,
                fact_id=fact.pk,
                decision=fields["decision"],
                review_note=fields["review_note"],
                review_confirmed=fields["review_confirmed"],
                source_checked=fields["source_checked"],
                season_checked=fields["season_checked"],
            )
        except ValueError as exc:
            is_stale = "Stale dossier version" in str(exc)
            return _render(
                request, job=job, dossier=base, fact=fact, form=form,
                status=409 if is_stale else 400,
                error=(
                    "Das Dossier wurde geändert. Bitte neu laden."
                    if is_stale else _review_problem(exc)
                ),
            )

    return redirect(
        f"{reverse('research-job', kwargs={'job_id': job.pk})}"
        f"?version={updated.version}#facts-heading"
    )
