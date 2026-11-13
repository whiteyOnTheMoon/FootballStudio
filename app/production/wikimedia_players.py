"""FS-014a: free, bounded Wikidata P54 player candidates for one owned club.

A Wikipedia/Wikidata sitelinks count is merely a *sampling heuristic*, not
evidence of "legend" status. These are unverified team-association candidates,
not approved legends, not narration, and never FactReview records.
"""
from datetime import datetime, timedelta, timezone
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from django.db import transaction
from django.utils import timezone as django_timezone

from .dossier_versions import fork_dossier
from .models import Evidence, Fact, FactDossier, ProductionJob, SourceReference
from .wikimedia_auto import AutoResearchError, _NoRedirect

_QID = re.compile(r"Q[1-9][0-9]{0,11}\Z")
_NAME = re.compile(r"[^<>\r\n\t]{2,120}\Z")
_ITEM = re.compile(r"https?://www\.wikidata\.org/entity/(Q[1-9][0-9]{0,11})\Z")
_SPARQL_URL = "https://query.wikidata.org/sparql"
_MAX_RESULTS = 12
_MAX_SAVED = 8
_MAX_BYTES = 128_000
_TIMEOUT = 8
_MIN_SITELINKS = 3
_MARKER_PREFIX = "auto-p54:"
_HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "FootballStudio/0.1 (https://github.com/whiteyOnTheMoon/FootballStudio)",
}


def _query(qid):
    if type(qid) is not str or not _QID.fullmatch(qid):
        raise AutoResearchError("invalid_club_qid")
    # Exact club ID, not a fuzzy text search or an unbounded Wikidata scan.
    return (
        "SELECT DISTINCT ?person ?name ?sitelinks WHERE { "
        f"?person wdt:P54 wd:{qid} ; "
        "wdt:P31 wd:Q5 ; "
        "wdt:P106 wd:Q937857 ; "
        "wikibase:sitelinks ?sitelinks ; "
        "rdfs:label ?name . "
        'FILTER(LANG(?name) = "en") '
        f"FILTER(?sitelinks >= {_MIN_SITELINKS}) "
        "} ORDER BY DESC(?sitelinks) ?person "
        f"LIMIT {_MAX_RESULTS}"
    )


def _parse(payload):
    if not isinstance(payload, dict):
        raise AutoResearchError("invalid_response")
    results = payload.get("results")
    rows = results.get("bindings") if isinstance(results, dict) else None
    if not isinstance(rows, list) or len(rows) > _MAX_RESULTS:
        raise AutoResearchError("invalid_response")
    found = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        who, name, links = (
            item.get("person"), item.get("name"), item.get("sitelinks"),
        )
        if not all(isinstance(v, dict) for v in (who, name, links)):
            continue
        if who.get("type") != "uri" or type(who.get("value")) is not str:
            continue
        m = _ITEM.fullmatch(who["value"])
        if m is None:
            continue
        person_qid = m.group(1)
        label = name.get("value")
        if (
            name.get("type") != "literal" or name.get("xml:lang") != "en"
            or type(label) is not str or not _NAME.fullmatch(label)
            or label != label.strip() or not label.isprintable()
        ):
            continue
        raw_count = links.get("value")
        if (
            links.get("type") != "literal"
            or type(raw_count) is not str
            or not re.fullmatch(r"[0-9]{1,4}", raw_count)
        ):
            continue
        count = int(raw_count)
        if not _MIN_SITELINKS <= count <= 9999:
            continue
        candidate = {"person_qid": person_qid, "name": label, "sitelinks": count}
        if person_qid in found and found[person_qid] != candidate:
            raise AutoResearchError("conflicting_candidate")
        found[person_qid] = candidate
    return sorted(
        found.values(), key=lambda row: (-row["sitelinks"], row["person_qid"]),
    )[:_MAX_SAVED]


def discover_wikidata_players(*, club_qid):
    """One 8s capped WDQS call; no site crawling and no paid provider."""
    sparql = _query(club_qid)
    request = Request(
        _SPARQL_URL + "?" + urlencode({"query": sparql, "format": "json"}),
        headers=_HEADERS,
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=_TIMEOUT) as response:
            raw = response.read(_MAX_BYTES + 1)
    except HTTPError as exc:
        raise AutoResearchError(
            "service_busy" if exc.code in (429, 503) else "upstream_error",
        ) from None
    except (URLError, TimeoutError, OSError):
        raise AutoResearchError("network_error") from None
    if len(raw) > _MAX_BYTES:
        raise AutoResearchError("response_too_large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise AutoResearchError("invalid_response") from None
    candidates = _parse(data)
    if not candidates:
        raise AutoResearchError("no_people_candidates")
    return candidates


def _latest(job):
    return FactDossier.objects.filter(job=job).order_by("-version").first()


def _marker(qid):
    return _MARKER_PREFIX + qid


def _previously_scanned(dossier, qid):
    return dossier.sources.filter(
        source_kind=SourceReference.Kind.WIKIDATA,
        external_id=_marker(qid),
        url=_SPARQL_URL,
    ).exists()


def import_wikidata_player_candidates(*, owner, job_id, expected_version):
    """Append 1-8 unverified player candidates to a new dossier version once.

    Owner, latest version and a preexisting auto-discovered club Q-ID are
    required before one outbound query. No user-controlled Q-ID or URL.
    Existing facts and past snapshots remain untouched.
    """
    owner_id = getattr(owner, "pk", None)
    if (
        type(owner_id) is not int or owner_id <= 0
        or type(job_id) is not int or job_id <= 0
        or type(expected_version) is not int or expected_version <= 0
    ):
        raise AutoResearchError("invalid_request")
    job = ProductionJob.objects.filter(
        pk=job_id, owner_id=owner_id,
    ).first()
    if job is None:
        raise AutoResearchError("not_authorized")
    previous = _latest(job)
    if previous is None:
        raise AutoResearchError("no_auto_research")
    sources = list(previous.sources.filter(
        source_kind=SourceReference.Kind.WIKIDATA,
        title__startswith="[auto] ",
        external_id__regex=r"^Q[1-9][0-9]{0,11}$",
    ).order_by("pk")[:2])
    if len(sources) != 1:
        raise AutoResearchError("no_auto_research")
    club_qid = sources[0].external_id
    expected_url = (
        "https://www.wikidata.org/wiki/Special:EntityData/"
        + club_qid + ".json"
    )
    if sources[0].url != expected_url:
        raise AutoResearchError("invalid_club_source")
    if _previously_scanned(previous, club_qid):
        return previous
    if previous.version != expected_version:
        raise AutoResearchError("stale_dossier")
    candidates = discover_wikidata_players(club_qid=club_qid)

    with transaction.atomic():
        locked = ProductionJob.objects.select_for_update().get(
            pk=job.pk, owner_id=owner_id,
        )
        latest = _latest(locked)
        if latest is None:
            raise AutoResearchError("stale_dossier")
        if _previously_scanned(latest, club_qid):
            return latest
        if latest.version != expected_version or not latest.sources.filter(
            source_kind=SourceReference.Kind.WIKIDATA,
            external_id=club_qid, url=expected_url,
            title__startswith="[auto] ",
        ).exists():
            raise AutoResearchError("stale_dossier")
        if FactDossier.objects.filter(
            job=locked,
            created_at__gte=django_timezone.now() - timedelta(minutes=1),
        ).count() >= 10:
            raise AutoResearchError("version_rate_limited")

        dossier = fork_dossier(job=locked, previous=latest)
        retrieved_at = datetime.now(timezone.utc)
        SourceReference.objects.create(
            dossier=dossier, source_kind=SourceReference.Kind.WIKIDATA,
            url=_SPARQL_URL,
            external_id=_marker(club_qid),
            title="Wikidata P54 player-candidate discovery (not legends)",
            retrieved_at=retrieved_at,
            access_state=SourceReference.Access.ACCESSIBLE,
        )
        previously_known = {
            item.value.get("person_qid") for item in dossier.facts.filter(
                predicate="club_player_candidate",
            ) if isinstance(item.value, dict)
        }
        for candidate in candidates:
            qid = candidate["person_qid"]
            if qid in previously_known:
                continue
            url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
            source = dossier.sources.filter(
                source_kind=SourceReference.Kind.WIKIDATA,
                external_id=qid, url=url,
            ).first()
            if source is None:
                source = SourceReference.objects.create(
                    dossier=dossier, source_kind=SourceReference.Kind.WIKIDATA,
                    url=url, external_id=qid,
                    title="Wikidata player candidate: " + candidate["name"][:210],
                    retrieved_at=retrieved_at,
                    access_state=SourceReference.Access.ACCESSIBLE,
                )
            fact = Fact.objects.create(
                dossier=dossier, predicate="club_player_candidate",
                value=candidate,
                assertion_text=(
                    f"Wikidata records a team association for {candidate['name']}."
                ),
                verification_state=Fact.Verification.UNVERIFIED,
            )
            Evidence.objects.create(
                fact=fact, source=source, role=Evidence.Role.UNKNOWN,
                locator=f"Wikidata {qid} · member of sports team (P54) → {club_qid}",
                summary=(
                    f"The bounded Wikidata query lists {qid} as associated "
                    f"with club {club_qid} through P54. "
                    "Not evidence of official legend status or a human review."
                ),
            )
        return dossier
