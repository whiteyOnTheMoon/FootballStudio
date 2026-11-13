"""Owner-only explicit free Wikimedia research trigger; no manual Q-ID needed."""
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from urllib.parse import urlencode

from .models import FactDossier, ProductionJob
from .wikimedia_auto import AutoResearchError, import_free_club_research


_MESSAGES = {
    "no_confident_match": (
        "Kein eindeutig zuordenbarer Wikidata-Fußballverein gefunden. "
        "Die Recherche hat keine Fakten gespeichert."
    ),
    "ambiguous_entity": (
        "Mehrere passende Vereine gefunden. Zur Vermeidung einer falschen "
        "Zuordnung wurden keine Fakten übernommen."
    ),
    "network_error": "Wikimedia ist derzeit nicht erreichbar. Es wurden keine Fakten gespeichert.",
    "service_busy": "Wikimedia ist momentan überlastet. Bitte später erneut versuchen.",
    "stale_dossier": "Der Forschungsstand hat sich geändert. Bitte das Dossier neu öffnen.",
}
_DEFAULT = (
    "Die freie Recherche konnte nicht sicher abgeschlossen werden. "
    "Es wurden keine unbestätigten Daten automatisch freigegeben."
)


@login_required
@require_POST
@never_cache
def start_free_wikimedia_research(request, job_id):
    """GET cannot trigger network; CSRF is checked by Django middleware."""
    job = get_object_or_404(
        ProductionJob, pk=job_id, owner=request.user,
    )
    raw = request.POST.get("expected_version")
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal():
        raise Http404("Ungültige Dossierversion.")
    if len(raw) > 9 or (len(raw) > 1 and raw.startswith("0")):
        raise Http404("Ungültige Dossierversion.")
    version = int(raw)
    if version < 0:
        raise Http404("Ungültige Dossierversion.")
    try:
        dossier = import_free_club_research(
            owner=request.user, job_id=job.pk, expected_version=version,
        )
    except AutoResearchError as exc:
        return HttpResponse(
            _MESSAGES.get(exc.code, _DEFAULT),
            status=409 if exc.code in (
                "ambiguous_entity", "no_confident_match", "stale_dossier",
            ) else 503,
            content_type="text/plain; charset=utf-8",
        )
    url = reverse("research-job", kwargs={"job_id": job.pk})
    return redirect(url + "?" + urlencode({"version": dossier.version}))


@login_required
@require_POST
@never_cache
def enrich_free_wikimedia_stadium(request, job_id):
    """Use the already associated Q-ID, never arbitrary user-supplied URLs."""
    from .wikimedia_stadium import enrich_wikimedia_stadium

    job = get_object_or_404(ProductionJob, pk=job_id, owner=request.user)
    raw = request.POST.get("expected_version")
    if (
        type(raw) is not str or not raw.isascii() or not raw.isdecimal()
        or not 1 <= len(raw) <= 9
        or raw.startswith("0")
    ):
        raise Http404("Ungültige Dossierversion.")
    version = int(raw)
    try:
        dossier = enrich_wikimedia_stadium(
            owner=request.user, job_id=job.pk, expected_version=version,
        )
    except AutoResearchError as exc:
        messages = {
            "no_auto_research": (
                "Bitte zuerst die automatische Wikidata-Vereinsrecherche "
                "starten; es liegt noch keine eindeutige Vereinszuordnung vor."
            ),
            "no_stadium_candidate": (
                "Wikidata enthält keine eindeutige aktuelle Heimspielstätte. "
                "Es wurde nichts erfunden oder gespeichert."
            ),
            "ambiguous_stadium": (
                "Wikidata nennt mehrere mögliche Heimspielstätten. "
                "Es wurde kein Stadion automatisch ausgewählt."
            ),
            "missing_stadium_label": (
                "Für das Stadion fehlt ein geeigneter englischer Name. "
                "Es wurde kein Faktenvorschlag gespeichert."
            ),
        }
        return HttpResponse(
            messages.get(exc.code, _MESSAGES.get(exc.code, _DEFAULT)),
            status=503 if exc.code in ("network_error", "service_busy", "upstream_error")
            else 409,
            content_type="text/plain; charset=utf-8",
        )
    url = reverse("research-job", kwargs={"job_id": job.pk})
    return redirect(url + "?" + urlencode({"version": dossier.version}))


@login_required
@require_POST
@never_cache
def discover_free_wikimedia_players(request, job_id):
    """Search bounded P54 candidates for the owner's auto-identified club."""
    from .wikimedia_players import import_wikidata_player_candidates

    job = get_object_or_404(ProductionJob, pk=job_id, owner=request.user)
    raw = request.POST.get("expected_version")
    if (
        type(raw) is not str or not raw.isascii() or not raw.isdecimal()
        or not 1 <= len(raw) <= 9 or raw.startswith("0")
    ):
        raise Http404("Ungültige Dossierversion.")
    try:
        dossier = import_wikidata_player_candidates(
            owner=request.user, job_id=job.pk, expected_version=int(raw),
        )
    except AutoResearchError as exc:
        errors = {
            "no_people_candidates": (
                "Wikidata bietet für diesen Verein derzeit keine geeigneten "
                "Spieler-Kandidaten mit nachvollziehbarer Vereinszugehörigkeit."
            ),
            "no_auto_research": (
                "Bitte zuerst die automatische Vereinszuordnung durchführen."
            ),
            "version_rate_limited": (
                "Zu viele neue Recherchestände in kurzer Zeit. "
                "Bitte die bestehende Dossierversion verwenden."
            ),
            "conflicting_candidate": (
                "Widersprüchliche Personenangaben wurden gefunden. "
                "Die Kandidaten wurden nicht übernommen."
            ),
        }
        return HttpResponse(
            errors.get(exc.code, _MESSAGES.get(exc.code, _DEFAULT)),
            status=503 if exc.code in ("network_error", "service_busy", "upstream_error")
            else 409,
            content_type="text/plain; charset=utf-8",
        )
    url = reverse("research-job", kwargs={"job_id": job.pk})
    return redirect(url + "?" + urlencode({"version": dossier.version}))
