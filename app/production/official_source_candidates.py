"""FS-014e: free, bounded official-website *candidates* from Wikidata P856.

This does not confirm a club/league domain, terms, access or fact accuracy.
The sole outbound lookups use the existing fixed-host Wikidata HTTPS adapter;
the proposed URLs are NEVER fetched or followed by this module.
"""
from datetime import timedelta
import re
import unicodedata

from django.db import transaction
from django.utils import timezone

from .dossier_versions import fork_dossier
from .manual_source_import import validate_manual_source_url
from .models import Evidence, Fact, FactDossier, ProductionJob, SourceReference
from .wikimedia_auto import (
    AutoResearchError, _claims, _entity, _linked_ids, _statement_value, _iso_country,
)

_QID = re.compile(r"Q[1-9][0-9]{0,11}\Z")
_WD_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/"
_MARKER = "auto-p856-sites:"
_LEAGUE_FILLERS = frozenset({
    "football", "soccer", "fussball", "fußball", "association", "the",
})


def _words(value):
    if type(value) is not str or not 2 <= len(value) <= 160:
        return ()
    value = unicodedata.normalize("NFKC", value).casefold()
    tokens = re.findall(r"[^\W_]+", value)
    return tuple(token for token in tokens if token not in _LEAGUE_FILLERS)


def _league_matches(entity, league_name):
    """Conservative equivalent name only; no vague substring match."""
    expected = _words(league_name)
    if not expected or not isinstance(entity, dict):
        return False
    names = []
    for language in ("en", "de"):
        for group in ("labels",):
            entry = entity.get(group, {})
            label = entry.get(language) if isinstance(entry, dict) else None
            if isinstance(label, dict) and type(label.get("value")) is str:
                names.append(label["value"])
        aliases = entity.get("aliases", {})
        alternatives = aliases.get(language, []) if isinstance(aliases, dict) else []
        if isinstance(alternatives, list):
            for alias in alternatives[:8]:
                if isinstance(alias, dict) and type(alias.get("value")) is str:
                    names.append(alias["value"])
    return any(_words(name) == expected for name in names)


def _one_p856(entity):
    """Accept exactly one safe public HTTPS URL, or report no candidate."""
    urls = set()
    try:
        statements = _claims(entity, "P856")
    except AutoResearchError:
        return None
    for stmt in statements:
        value = _statement_value(stmt)
        if type(value) is not str:
            continue
        try:
            canonical, _host = validate_manual_source_url(value)
        except ValueError:
            continue
        if len(canonical) <= 500:
            urls.add(canonical)
    return next(iter(urls)) if len(urls) == 1 else None


def _confirmed_club_qid(dossier):
    if dossier is None:
        raise AutoResearchError("no_auto_research")
    rows = list(dossier.sources.filter(
        source_kind=SourceReference.Kind.WIKIDATA,
        title__startswith="[auto] ",
        external_id__regex=r"^Q[1-9][0-9]{0,11}$",
    ).order_by("pk")[:2])
    if len(rows) != 1:
        raise AutoResearchError("no_auto_research")
    qid = rows[0].external_id
    if (
        not _QID.fullmatch(qid)
        or rows[0].url != _WD_ENTITY + qid + ".json"
    ):
        raise AutoResearchError("invalid_club_source")
    return qid


def _already_scanned(dossier, qid):
    return dossier.sources.filter(
        source_kind=SourceReference.Kind.WIKIDATA,
        external_id=_MARKER + qid,
        url=_WD_ENTITY + qid + ".json",
    ).exists()


def discover_official_site_candidates(*, club_qid, league_name, country_code):
    """Only a known club QID, max 4 P118 league entities + limited P17 checks."""
    if (
        type(club_qid) is not str or not _QID.fullmatch(club_qid)
        or not _words(league_name)
        or type(country_code) is not str
        or not re.fullmatch(r"[A-Z]{2}", country_code)
    ):
        raise AutoResearchError("invalid_request")
    club = _entity(club_qid)
    club_site = _one_p856(club)
    league_ids = _linked_ids(club, "P118")[:4]
    accepted = []
    for league_qid in league_ids:
        if league_qid == club_qid:
            continue
        entity = _entity(league_qid)
        if not _league_matches(entity, league_name):
            continue
        countries = _linked_ids(entity, "P17")[:2]
        if not countries or not any(
            country_code in _iso_country(qid) for qid in countries
        ):
            continue
        site = _one_p856(entity)
        if site is not None:
            accepted.append((league_qid, site))
    # Multiple plausible league objects/URLs mean no authoritative candidate.
    accepted = list(dict.fromkeys(accepted))
    league = accepted[0] if len(accepted) == 1 else None
    return {
        "club_qid": club_qid,
        "club_url": club_site,
        "league_qid": league[0] if league else None,
        "league_url": league[1] if league else None,
    }


def import_official_site_candidates(*, owner, job_id, expected_version):
    """One research action, no content download and NO SourceConfirmation."""
    owner_id = getattr(owner, "pk", None)
    if (
        type(owner_id) is not int or owner_id <= 0
        or type(job_id) is not int or job_id <= 0
        or type(expected_version) is not int or expected_version < 1
    ):
        raise AutoResearchError("invalid_request")
    job = ProductionJob.objects.filter(
        pk=job_id, owner_id=owner_id,
    ).first()
    if job is None:
        raise AutoResearchError("not_authorized")
    latest = FactDossier.objects.filter(job=job).order_by("-version").first()
    qid = _confirmed_club_qid(latest)
    if _already_scanned(latest, qid):
        return latest
    if latest.version != expected_version:
        raise AutoResearchError("stale_dossier")
    found = discover_official_site_candidates(
        club_qid=qid, league_name=job.league_name,
        country_code=job.country_code,
    )
    with transaction.atomic():
        locked = ProductionJob.objects.select_for_update().get(
            pk=job.pk, owner_id=owner_id,
        )
        current = FactDossier.objects.filter(
            job=locked,
        ).order_by("-version").first()
        if current is None:
            raise AutoResearchError("stale_dossier")
        if _already_scanned(current, qid):
            return current
        if current.version != expected_version or _confirmed_club_qid(current) != qid:
            raise AutoResearchError("stale_dossier")
        if FactDossier.objects.filter(
            job=locked, created_at__gte=timezone.now()-timedelta(minutes=1),
        ).count() >= 10:
            raise AutoResearchError("version_rate_limited")

        dossier = fork_dossier(job=locked, previous=current)
        now = timezone.now()
        # Marker is not a claim of fetching or approving any official domain.
        club_source = dossier.sources.get(
            source_kind=SourceReference.Kind.WIKIDATA,
            external_id=qid,
            url=_WD_ENTITY + qid + ".json",
        )
        SourceReference.objects.create(
            dossier=dossier,
            source_kind=SourceReference.Kind.WIKIDATA,
            url=_WD_ENTITY + qid + ".json",
            title="Wikidata P856 official-site candidate lookup (not consent)",
            external_id=_MARKER + qid,
            retrieved_at=now,
            access_state=SourceReference.Access.ACCESSIBLE,
        )
        for context, source_qid, site_url, title, predicate in (
            ("club", qid, found["club_url"], f"Club {locked.club_name}",
             "official_club_site_candidate"),
            ("league", found["league_qid"], found["league_url"],
             f"League {locked.league_name}", "official_league_site_candidate"),
        ):
            if not site_url or not source_qid:
                continue
            if context == "club":
                evidence_source = club_source
            else:
                evidence_source = SourceReference.objects.create(
                    dossier=dossier,
                    source_kind=SourceReference.Kind.WIKIDATA,
                    url=_WD_ENTITY + source_qid + ".json",
                    title=f"Wikidata league item ({locked.league_name})"[:250],
                    external_id="auto-league-entity:" + source_qid,
                    retrieved_at=now,
                    access_state=SourceReference.Access.ACCESSIBLE,
                )
            fact = Fact.objects.create(
                dossier=dossier,
                predicate=predicate,
                value={
                    "url": site_url, "context": context,
                    "wikidata_qid": source_qid,
                    "provenance": "Wikidata P856 candidate",
                },
                assertion_text=(
                    f"Wikidata lists {site_url} as an official website "
                    f"for {title}; the URL has not been independently confirmed."
                ),
                verification_state=Fact.Verification.UNVERIFIED,
            )
            Evidence.objects.create(
                fact=fact, source=evidence_source,
                role=Evidence.Role.UNKNOWN,
                locator=f"Wikidata {source_qid} · official website (P856)",
                summary=(
                    "URL candidate only; no automatic access, site identity "
                    "confirmation, terms approval or editorial fact review."
                ),
            )
        return dossier



def proposed_site_for_context(dossier, context):
    """Read one saved P856 suggestion for a read-only form prefill.

    This is NOT authorization for automatic crawling; the manual source
    registration service still validates the URL and requires all three
    fresh, independent checkbox attestations.
    """
    if context not in ("club", "league") or dossier is None:
        return None
    try:
        club_qid = _confirmed_club_qid(dossier)
    except AutoResearchError:
        return None
    if not _already_scanned(dossier, club_qid):
        return None
    predicate = (
        "official_club_site_candidate" if context == "club"
        else "official_league_site_candidate"
    )
    matches = list(dossier.facts.filter(
        predicate=predicate,
        verification_state=Fact.Verification.UNVERIFIED,
    ).prefetch_related("evidence__source").order_by("pk")[:2])
    if len(matches) != 1:
        return None
    fact = matches[0]
    value = fact.value
    if not isinstance(value, dict) or value.get("context") != context:
        return None
    url, qid = value.get("url"), value.get("wikidata_qid")
    if (
        type(qid) is not str or not _QID.fullmatch(qid)
        or (context == "club" and qid != club_qid)
        or (context == "league" and qid == club_qid)
        or type(url) is not str
    ):
        return None
    try:
        validated, _ = validate_manual_source_url(url)
    except ValueError:
        return None
    if validated != url:
        return None
    good_evidence = any(
        item.source.source_kind == SourceReference.Kind.WIKIDATA
        and item.source.url == _WD_ENTITY + qid + ".json"
        and item.locator == f"Wikidata {qid} · official website (P856)"
        for item in fact.evidence.all()
    )
    if not good_evidence:
        return None
    confirmed = dossier.sources.filter(
        source_kind=(
            SourceReference.Kind.CLUB_OFFICIAL if context == "club"
            else SourceReference.Kind.LEAGUE_OFFICIAL
        ),
        url=url, manual_confirmation__isnull=False,
    ).exists()
    return {
        "context": context, "url": url, "qid": qid,
        "confirmed": confirmed,
        "title": (
            f"Offizielle Vereinswebsite · {dossier.job.club_name}"
            if context == "club"
            else f"Offizielle Ligawebsite · {dossier.job.league_name}"
        )[:160],
    }
