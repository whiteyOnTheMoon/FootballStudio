"""Owner-scoped, opt-in import of *source metadata* from official-site research.

A source reference is NOT a verified claim. This module neither scrapes new
sites independently nor stores article bodies; it calls only the already
guarded research service after independent manual site/terms confirmation.
No HTTP entry point or automatic worker is wired to this function.
"""
from datetime import datetime, timedelta, timezone

from django.db import transaction

from .dossier_versions import fork_dossier
from .models import FactDossier, ProductionJob, SourceReference
from .official_site_research import research_official_website
from .safe_official_fetch import WebsiteFetchError, _checked_url


_MAX_PAGES = 4
_CATEGORIES = {
    "club": {"history", "honours", "stadium", "about", "team"},
    "league": {"standings", "fixtures", "results", "competition", "clubs", "statistics"},
}


def _source_kind(context):
    if context not in _CATEGORIES:
        raise ValueError("Only official club and league sources may be imported.")
    return (
        SourceReference.Kind.CLUB_OFFICIAL if context == "club"
        else SourceReference.Kind.LEAGUE_OFFICIAL
    )


def _latest(job):
    return FactDossier.objects.filter(job=job).order_by("-version").first()


def _already_imported(previous, *, homepage, kind):
    if previous is None:
        return False
    matches = previous.sources.filter(url=homepage)
    if matches.exclude(source_kind=kind).exists():
        raise ValueError("Conflicting source context for an existing website.")
    return matches.filter(source_kind=kind).exists()


def _parse_snapshot(snapshot, *, job, homepage, context, started_at):
    """Strictly limit persisted fields to the guarded research response."""
    expected_host = _checked_url(homepage)[1]
    if not isinstance(snapshot, dict) or (
        snapshot.get("job_id") != job.pk
        or snapshot.get("club_id") != job.club_id
        or snapshot.get("league_id") != job.club.league_id
        or snapshot.get("context") != context
        or snapshot.get("site_url") != homepage
        or snapshot.get("robots_url") != f"https://{expected_host}/robots.txt"
        or snapshot.get("source_status") != "unverified"
        or snapshot.get("stored") is not False
    ):
        raise WebsiteFetchError("invalid_snapshot")
    raw_pages = snapshot.get("pages")
    if not isinstance(raw_pages, list) or not 1 <= len(raw_pages) <= _MAX_PAGES:
        raise WebsiteFetchError("invalid_snapshot")

    now = datetime.now(timezone.utc)
    result, seen = [], set()
    for index, page in enumerate(raw_pages):
        if not isinstance(page, dict):
            raise WebsiteFetchError("invalid_snapshot")
        try:
            page_url, host = _checked_url(page.get("url"))
        except WebsiteFetchError:
            raise WebsiteFetchError("invalid_snapshot") from None
        if (
            host != expected_host
            or page_url != page.get("url")
            or page_url in seen
            or len(page_url) > 750
            or (index == 0 and page_url != homepage)
            or (index > 0 and page_url == homepage)
            or page.get("verification_state") != "unverified"
        ):
            raise WebsiteFetchError("invalid_snapshot")
        if index > 0 and page.get("category") not in _CATEGORIES[context]:
            raise WebsiteFetchError("invalid_snapshot")

        title = page.get("title")
        headings = page.get("headings")
        if (
            not isinstance(title, str) or len(title) > 160
            or not isinstance(headings, list) or len(headings) > 5
            or any(not isinstance(h, str) or len(h) > 160 for h in headings)
        ):
            raise WebsiteFetchError("invalid_snapshot")
        try:
            retrieved_at = datetime.fromisoformat(page["retrieved_at"])
        except (ValueError, TypeError, KeyError):
            raise WebsiteFetchError("invalid_snapshot") from None
        if (
            retrieved_at.tzinfo is None
            or retrieved_at.utcoffset() is None
            or retrieved_at < started_at - timedelta(minutes=2)
            or retrieved_at > now + timedelta(minutes=2)
        ):
            raise WebsiteFetchError("invalid_snapshot")
        result.append({
            "url": page_url,
            "title": title,
            "retrieved_at": retrieved_at,
        })
        seen.add(page_url)

    return result


def import_official_site_sources(*, owner, job_id, homepage_url, context,
                                 identity_confirmed=False, terms_confirmed=False):
    """Import up to four page references as a NEW complete dossier version.

    A repeat of the identical confirmed homepage uses the latest version and
    performs no new network request. Refresh/replacement is deliberately NOT
    supported here; preserving old source timestamps and evidence matters.
    """
    if identity_confirmed is not True or terms_confirmed is not True:
        raise ValueError("Explicit website identity and site-terms confirmation required.")
    kind = _source_kind(context)
    homepage, _ = _checked_url(homepage_url)

    # Permission check before ANY network activity, including robots.txt.
    job = ProductionJob.objects.select_related("club__league").get(
        pk=job_id, owner=owner,
    )
    previous = _latest(job)
    if _already_imported(previous, homepage=homepage, kind=kind):
        return previous

    started_at = datetime.now(timezone.utc)
    research = research_official_website(
        owner=owner, job_id=job_id, homepage_url=homepage, context=context,
        identity_confirmed=True, terms_confirmed=True,
    )
    pages = _parse_snapshot(
        research, job=job, homepage=homepage, context=context,
        started_at=started_at,
    )

    # Never hold locks while making remote requests. Lock on commit to make
    # version allocation and concurrent same-website imports deterministic.
    with transaction.atomic():
        locked_job = ProductionJob.objects.select_for_update().get(
            pk=job_id, owner=owner,
        )
        previous = _latest(locked_job)
        if _already_imported(previous, homepage=homepage, kind=kind):
            return previous

        dossier = fork_dossier(job=locked_job, previous=previous)
        existing = {source.url: source.source_kind for source in dossier.sources.all()}
        for page in pages:
            if page["url"] in existing:
                if existing[page["url"]] != kind:
                    raise ValueError("Conflicting source kind for duplicate URL.")
                continue
            source = SourceReference(
                dossier=dossier, url=page["url"],
                source_kind=kind, title=page["title"],
                external_id="", retrieved_at=page["retrieved_at"],
                access_state=SourceReference.Access.ACCESSIBLE,
            )
            source.full_clean()
            source.save()
            existing[page["url"]] = kind
        return dossier
