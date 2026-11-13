"""Owner-only scene storyboard preview and explicit save (FS-016c).

GET never writes; POST checks CSRF, dossier version, owner and a fresh draft
fingerprint before persisting. No paid calls, TTS, media download or rendering.
"""
import re
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import FactDossier, ProductionJob, ScenePlanSnapshot
from .scene_plan import ScenePlanError, build_scene_plan
from .scene_snapshots import (
    SceneSnapshotError, load_scene_plan_snapshot, save_scene_plan_snapshot,
)
from .script_draft import ScriptDraftError, load_job_script_draft


_WPM_OPTIONS = (120, 145, 165)
_MESSAGES = {
    "no_reviewed_facts": (
        "Noch keine geeigneten, menschlich überprüften Fakten vorhanden. "
        "Bitte zuerst Belege und Reviewentscheidungen im Dossier ergänzen."
    ),
    "stale_scene_snapshot": (
        "Der gespeicherte Plan ist veraltet. Ein neuer Dossierstand "
        "ist erforderlich; vorhandene Pläne werden nicht überschrieben."
    ),
    "corrupt_scene_snapshot": (
        "Der gespeicherte Szenenplan hat die Integritätsprüfung nicht bestanden."
    ),
}
_DEFAULT_MESSAGE = (
    "Für diesen Forschungsstand kann derzeit kein sicherer Szenenplan "
    "erstellt oder geladen werden."
)


def _positive_version(raw):
    if not isinstance(raw, str) or not re.fullmatch(r"[1-9][0-9]{0,8}", raw):
        raise Http404("Ungültige Dossierversion.")
    return int(raw)


def _wpm(raw):
    if not isinstance(raw, str) or not re.fullmatch(r"[1-9][0-9]{2}", raw):
        raise Http404("Ungültiges Sprechtempo.")
    value = int(raw)
    if value not in _WPM_OPTIONS:
        raise Http404("Unbekanntes Sprechtempo.")
    return value


def _preview(owner, job_id, version, rate):
    draft = load_job_script_draft(
        owner=owner, job_id=job_id, version=version,
    )
    return build_scene_plan(draft, words_per_minute=rate)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def scene_storyboard(request, job_id):
    job = get_object_or_404(ProductionJob, pk=job_id, owner=request.user)
    latest = FactDossier.objects.filter(job=job).order_by("-version").first()
    if latest is None:
        raise Http404("Kein Faktendossier vorhanden.")

    params = request.POST if request.method == "POST" else request.GET
    raw_version = params.get("version")
    version = latest.version if raw_version is None and request.method == "GET" else (
        _positive_version(raw_version)
    )
    if not FactDossier.objects.filter(job=job, version=version).exists():
        raise Http404("Dossierversion nicht vorhanden.")
    rate = _wpm(params.get("wpm", "145"))

    if request.method == "POST" and version != latest.version:
        return HttpResponse(
            "Nur der aktuelle Dossierstand darf neu gespeichert werden.",
            status=409, content_type="text/plain",
        )

    plan = None
    error_message = None
    saved = False
    try:
        plan = _preview(request.user, job.pk, version, rate)
        exists = ScenePlanSnapshot.objects.filter(
            job=job, dossier_version=version,
            words_per_minute=rate,
        ).exists()
        if exists:
            # Read-back validates stored checksum and equality to current
            # owner-scoped dossier; do not trust a checksum as authorization.
            load_scene_plan_snapshot(
                owner=request.user, job_id=job.pk,
                dossier_version=version, words_per_minute=rate,
            )
            saved = True
    except (ScriptDraftError, ScenePlanError, SceneSnapshotError) as exc:
        error_message = _MESSAGES.get(exc.code, _DEFAULT_MESSAGE)

    if request.method == "POST":
        fingerprint = params.get("expected_fingerprint", "")
        if (
            error_message or plan is None or saved
            or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
            or fingerprint != plan["plan_fingerprint_sha256"]
        ):
            return HttpResponse(
                "Die Vorschau hat sich geändert oder ist nicht speicherbar. "
                "Bitte den aktuellen Stand erneut öffnen.",
                status=409, content_type="text/plain",
            )
        try:
            save_scene_plan_snapshot(
                owner=request.user, job_id=job.pk,
                dossier_version=version, words_per_minute=rate,
            )
        except SceneSnapshotError:
            return HttpResponse(
                "Der Szenenplan konnte nicht sicher gespeichert werden. "
                "Bitte den Dossierstand erneut prüfen.",
                status=409, content_type="text/plain",
            )
        url = reverse("research-scene-plan", kwargs={"job_id":job.pk})
        return redirect(url + "?" + urlencode({"version": version, "wpm": rate}))

    scene_cards = []
    if plan is not None and error_message is None:
        for scene in plan["scenes"]:
            scene_cards.append({
                **scene,
                "duration_seconds": round(scene["duration_ms_estimate"] / 1000, 1),
            })

    return render(request, "studio/scene_storyboard.html", {
        "job": job, "version": version,
        "latest_version": latest.version,
        "wpm": rate, "wpm_options": _WPM_OPTIONS,
        "plan": plan if error_message is None else None,
        "scene_cards": scene_cards,
        "saved": saved,
        "error_message": error_message,
        "estimated_minutes": (
            round(plan["estimated_total_ms"] / 60000, 2)
            if plan is not None and error_message is None else None
        ),
        "length_label": (
            {
                "too_short": "Zu kurz für 8–10 Minuten",
                "too_long": "Zu lang für 8–10 Minuten",
                "within_target": "Geschätzte Länge im Zielbereich",
            }.get(plan["script_length_status"])
            if plan is not None and error_message is None else ""
        ),
    })
