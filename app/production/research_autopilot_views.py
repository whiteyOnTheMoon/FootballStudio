"""Owner-only research autopilot: one guarded import stage per POST.

When the browser sends Accept: application/json, it can safely resume the
next step after the previous request commits. Normal HTML form submission
falls back to one step and a redirect. GET never triggers external I/O.
"""
import re

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import ProductionJob
from .research_autopilot import execute_next_research
from .wikimedia_auto import AutoResearchError


_MESSAGES = {
    "stale_dossier": (
        "Die Dossierversion hat sich inzwischen geändert. "
        "Bitte den aktuellen Recherchestand neu öffnen."
    ),
    "no_confident_match": (
        "Der Verein konnte in Wikidata nicht eindeutig zugeordnet werden. "
        "Keine automatische Übernahme."
    ),
    "ambiguous_entity": (
        "Mehrere mögliche Vereinszuordnungen. Keine automatische Übernahme."
    ),
    "no_stadium_candidate": (
        "Keine eindeutige aktuelle Heimspielstätte gefunden. "
        "Die übrigen Recherchestufen bleiben erhalten."
    ),
    "ambiguous_stadium": (
        "Mehrdeutige Stadionangabe. Keine automatische Übernahme."
    ),
    "no_people_candidates": (
        "Für diesen Verein fehlen derzeit geeignete P54-Spielerkandidaten."
    ),
    "no_legend_sections": (
        "Die offizielle Vereinsseite enthält keine eindeutig auswertbare "
        "Legendenliste."
    ),
    "no_legend_names": (
        "Die offizielle Legendenliste konnte nicht sicher ausgelesen werden."
    ),
    "no_legend_matches": (
        "Kein eindeutiger Abgleich mit der offiziellen Legendenliste gefunden."
    ),
    "no_unique_legends_link": (
        "Keine eindeutig auffindbare offizielle Legendenliste."
    ),
    "no_confirmed_club_source": (
        "Für diesen Schritt ist noch keine zuvor bestätigte offizielle "
        "Vereinsquelle verfügbar. Sie wird nicht automatisch freigegeben."
    ),
    "no_confirmed_league_source": (
        "Für die Titelchronik fehlt eine zuvor bestätigte offizielle "
        "Ligaquelle. Sie wird nicht automatisch freigegeben."
    ),
    "invalid_honours_table": (
        "Die historische Ligatabelle konnte nicht eindeutig ausgewertet "
        "werden; keine Titel wurden erfunden."
    ),
    "no_honours_found": (
        "Aus der historischen Ligatabelle gingen keine eindeutigen Titel "
        "dieses Vereins hervor."
    ),
    "ambiguous_honours_table": (
        "Die Ligaquelle liefert widersprüchliche Titelangaben."
    ),
    "network_error": (
        "Die externe Quelle war nicht erreichbar. "
        "Bereits gespeicherte Recherchestufen bleiben erhalten."
    ),
    "service_busy": (
        "Der Rechercheanbieter ist überlastet. Keine automatische Wiederholung."
    ),
    "version_rate_limited": (
        "Es wurden bereits zu viele Dossierversionen in kurzer Zeit erzeugt."
    ),
}
_DEFAULT = (
    "Die automatische Recherche wurde sicher gestoppt. "
    "Bereits gespeicherte Ergebnisse bleiben erhalten."
)
_TITLES = {
    "club": "Vereinszuordnung",
    "stadium": "Stadionrecherche",
    "players": "Spielerrecherche",
    "legends": "Abgleich offizieller Vereinslegenden",
    "honours": "Meisterschafts- und Pokalchronik",
}


def _expects_json(request):
    return "application/json" in request.headers.get("Accept", "").lower()


@login_required
@require_POST
@never_cache
def continue_research(request, job_id):
    """Execute only one queued stage per user-authorized POST."""
    job = get_object_or_404(ProductionJob, pk=job_id, owner=request.user)
    raw = request.POST.get("expected_version")
    if type(raw) is not str or not re.fullmatch(r"(?:0|[1-9][0-9]{0,8})", raw):
        raise Http404("Ungültige Dossierversion.")
    try:
        result = execute_next_research(
            owner=request.user,
            job=job,
            expected_version=int(raw),
        )
    except AutoResearchError as exc:
        code = exc.code
        if code.startswith(("official_site_", "league_site_")):
            message = (
                "Die offizielle Website konnte unter den vorhandenen "
                "robots.txt-/Zugriffsregeln nicht sicher ausgewertet werden."
            )
        else:
            message = _MESSAGES.get(code, _DEFAULT)
        http_status = (
            503 if code in ("network_error", "service_busy", "upstream_error")
            or code.startswith(("official_site_", "league_site_"))
            else 409
        )
        if _expects_json(request):
            return JsonResponse({
                "status": "stopped",
                "message": message,
            }, status=http_status)
        return HttpResponse(
            message, content_type="text/plain; charset=utf-8",
            status=http_status,
        )

    plan = result["plan"]
    stage = result["stage"]
    version = plan["version"]
    state = (
        "advanced" if stage is not None
        else "complete" if plan["complete"]
        else "requires_sources" if plan["requires_source"]
        else "paused"
    )
    message = (
        f"Abgeschlossen: {_TITLES[stage]}."
        if stage is not None
        else "Die verfügbaren Recherchestufen sind bereits abgeschlossen."
        if plan["complete"]
        else "Keine weitere Recherche ohne zusätzliche bestätigte "
        "Quellen möglich."
        if plan["requires_source"]
        else "Es steht derzeit kein weiterer sicherer Rechercheschritt an."
    )
    if _expects_json(request):
        return JsonResponse({
            "status": state,
            "message": message,
            "version": version,
            "stage": stage,
            "next_stage": plan["next_id"],
            "completed": plan["completed"],
            "total": plan["total"],
            "requires_sources": plan["requires_source"],
        })
    url = reverse("research-job", kwargs={"job_id": job.pk})
    return redirect(url + (f"?version={version}" if version else ""))
