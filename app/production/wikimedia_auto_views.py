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
