"""No-network, manually confirmed official source registration for a job.

Identity/terms/access checkboxes are human attestations, never proof of
copyright permission, a server fetch, or the contents of the source. Any
automatic official-site fetching is handled separately by a robots/SSRF-
protected adapter and is NEVER invoked by this module.
"""
from datetime import timedelta
from urllib.parse import urlsplit

from django.db import transaction
from django.utils import timezone

from .dossier_versions import fork_dossier
from .fact_proposals import _short_text
from .models import FactDossier, ProductionJob, SourceConfirmation, SourceReference
from .safe_official_fetch import WebsiteFetchError, _checked_url


_DENIED_TLDS = frozenset({
    "local", "localhost", "internal", "lan", "home", "test",
    "invalid", "example", "onion", "arpa", "corp", "intranet",
})
_CONTEXT_KINDS = {
    "club": SourceReference.Kind.CLUB_OFFICIAL,
    "league": SourceReference.Kind.LEAGUE_OFFICIAL,
}
_MAX_WRITES_PER_MINUTE = 10


class ManualSourceStale(ValueError):
    """The user submitted against an older or otherwise changed snapshot."""


class ManualSourceConflict(ValueError):
    """This URL already has a different kind, metadata or provenance."""


class ManualSourceRateLimited(ValueError):
    """Too many new versions for this job in a single minute."""


def validate_manual_source_url(url):
    """Validate URL syntactically; never perform DNS, HTTP or URL follow-ups."""
    try:
        canonical, host = _checked_url(url)
    except WebsiteFetchError:
        raise ValueError("Only a public-looking HTTPS URL without port, login, query or fragment is accepted.") from None

    labels = host.split(".")
    if labels[-1] in _DENIED_TLDS or "transfermarkt" in labels:
        raise ValueError("This domain is not an eligible official club or league source.")
    if len(labels) < 2 or any(not label for label in labels):
        raise ValueError("A public DNS-style hostname is required.")
    if len(canonical) > 750:
        raise ValueError("URL too long.")
    if urlsplit(canonical).path.lower().endswith((
        ".exe", ".zip", ".tar", ".gz", ".mp4", ".mov", ".svg",
    )):
        raise ValueError("Direct download or executable media links are not supported.")
    return canonical, host


def register_manual_official_source(*, owner, job_id, expected_version,
                                    url, title, context, basis,
                                    identity_confirmed=False,
                                    terms_confirmed=False,
                                    access_confirmed=False):
    """Create a new full dossier version with attributed manual source metadata.

    expected_version == 0 is the only valid value for a job without a
    dossier. A verbatim retry can return the latest snapshot even after
    other changes; changed metadata is never silently overwritten.
    """
    if (identity_confirmed is not True or terms_confirmed is not True
            or access_confirmed is not True):
        raise ValueError("Identity, site terms and manual access must all be confirmed.")
    if type(expected_version) is not int or not 0 <= expected_version < 1_000_000_000:
        raise ValueError("An explicit, current dossier version is required.")
    if context not in _CONTEXT_KINDS:
        raise ValueError("Only club or league sources may be confirmed.")
    canonical, host = validate_manual_source_url(url)
    title = _short_text(title, "source title", min_length=4, max_length=160)
    basis = _short_text(basis, "confirmation basis", min_length=20, max_length=300)
    kind = _CONTEXT_KINDS[context]

    with transaction.atomic():
        job = ProductionJob.objects.select_for_update().get(
            pk=job_id, owner=owner,
        )
        latest = FactDossier.objects.filter(job=job).order_by("-version").first()
        if latest:
            matches = list(latest.sources.filter(url=canonical).select_related(
                "manual_confirmation"
            ))
            if matches:
                if len(matches) != 1:
                    raise ManualSourceConflict("URL already exists more than once.")
                existing = matches[0]
                confirmation = SourceConfirmation.objects.filter(source=existing).first()
                if (
                    existing.source_kind == kind
                    and existing.title == title
                    and existing.access_state == SourceReference.Access.ACCESSIBLE
                    and confirmation is not None
                    and confirmation.reviewer_id == owner.pk
                    and confirmation.confirmed_domain == host
                    and confirmation.basis == basis
                    and confirmation.identity_confirmed
                    and confirmation.terms_confirmed
                    and confirmation.access_confirmed
                ):
                    return latest
                raise ManualSourceConflict("URL already exists with different source metadata.")

        latest_version = latest.version if latest else 0
        if latest_version != expected_version:
            raise ManualSourceStale("Stale dossier version; reload before registering a source.")

        if FactDossier.objects.filter(
            job=job,
            created_at__gte=timezone.now() - timedelta(minutes=1),
        ).count() >= _MAX_WRITES_PER_MINUTE:
            raise ManualSourceRateLimited("Too many new dossier versions in one minute.")

        dossier = fork_dossier(job=job, previous=latest)
        checked_at = timezone.now()
        source = SourceReference(
            dossier=dossier, url=canonical, source_kind=kind,
            title=title, external_id="", retrieved_at=checked_at,
            access_state=SourceReference.Access.ACCESSIBLE,
        )
        source.full_clean()
        source.save()
        SourceConfirmation.objects.create(
            source=source, reviewer=owner, checked_at=checked_at,
            confirmed_domain=host, identity_confirmed=True,
            terms_confirmed=True, access_confirmed=True,
            basis=basis,
        )
        return dossier
