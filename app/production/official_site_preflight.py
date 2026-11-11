"""Fail-closed, offline preflight for a *manually* confirmed official source.

This module is only a plan for a possible future opt-in research run.
It NEVER calls DNS, HTTP, robots.txt, the crawling adapter, a worker,
or a paid provider. SourceConfirmation records a user's attestation,
not a server-verified domain, content licence or fact verification.

Callers must restrict sources to the latest, owner-scoped dossier.
"""
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from .manual_source_import import validate_manual_source_url
from .models import SourceReference
from .official_site_links import _CATEGORIES, _LEAGUE_CATEGORIES


# Subject areas, not guessed page URLs or promised live results.
_LABELS = {
    "history": "Vereinsgeschichte / Chronik",
    "honours": "Titel und Erfolge",
    "stadium": "Stadion",
    "standings": "Tabelle / Tabellenstände",
    "fixtures": "Spielplan",
    "results": "Ergebnisse",
}
_MAX_PAGES = 4
_MAX_SUBPAGES = 3


@dataclass(frozen=True)
class OfficialResearchPreflight:
    source_id: int
    context: str
    source_kind: str
    source_url: str
    source_title: str
    domain: str
    robots_url: str
    confirmation_reviewer_id: int
    confirmation_checked_at: object
    confirmation_basis: str
    themes: tuple
    max_total_pages: int = _MAX_PAGES
    max_subpages: int = _MAX_SUBPAGES


def plan_confirmed_official_source(source, *, owner_id, current_dossier_id):
    """Reject unconfirmed/mismatched sources *before* displaying a plan.

    All checks are local and deterministic. This does not authorize a
    subsequent network operation; the future worker must revalidate anew.
    """
    if (
        type(owner_id) is not int or owner_id <= 0
        or type(current_dossier_id) is not int or current_dossier_id <= 0
        or not isinstance(source, SourceReference)
        or source.dossier_id != current_dossier_id
        or source.dossier.job.owner_id != owner_id
        or source.access_state != SourceReference.Access.ACCESSIBLE
    ):
        return None

    contexts = {
        SourceReference.Kind.CLUB_OFFICIAL: ("club", _CATEGORIES),
        SourceReference.Kind.LEAGUE_OFFICIAL: ("league", _LEAGUE_CATEGORIES),
    }
    selected = contexts.get(source.source_kind)
    if selected is None:
        return None

    try:
        confirmation = source.manual_confirmation
    except SourceReference.manual_confirmation.RelatedObjectDoesNotExist:
        return None

    # Do not turn a historical or malformed attestation into network consent.
    if (
        confirmation.reviewer_id != owner_id
        or confirmation.identity_confirmed is not True
        or confirmation.terms_confirmed is not True
        or confirmation.access_confirmed is not True
        or not isinstance(confirmation.basis, str)
        or not 20 <= len(confirmation.basis.strip()) <= 300
        or "<" in confirmation.basis
        or confirmation.checked_at is None
        or timezone.is_naive(confirmation.checked_at)
        or confirmation.checked_at > timezone.now() + timedelta(minutes=5)
    ):
        return None

    try:
        canonical, host = validate_manual_source_url(source.url)
    except ValueError:
        return None
    if canonical != source.url or confirmation.confirmed_domain != host:
        return None

    context, categories = selected
    themes = tuple({
        "key": name,
        "name": _LABELS.get(name, name),
    } for name, _priority, _terms in categories[:_MAX_SUBPAGES])
    return OfficialResearchPreflight(
        source_id=source.pk,
        context=context,
        source_kind=source.source_kind,
        source_url=canonical,
        source_title=source.title,
        domain=host,
        robots_url=f"https://{host}/robots.txt",
        confirmation_reviewer_id=confirmation.reviewer_id,
        confirmation_checked_at=confirmation.checked_at,
        confirmation_basis=confirmation.basis,
        themes=themes,
    )
