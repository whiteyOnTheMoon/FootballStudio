"""Automatic, bounded *free* Wikidata/Wikipedia research for an owned club job.

One explicit POST (not a background worker) discovers the Wikidata Q-ID from
the club name, corroborates football-club class and ISO country, then stores
source-linked, UNVERIFIED fact candidates. Never fabricates human FactReview.
Only fixed Wikimedia HTTPS hosts are accessed, without redirects.
"""
from datetime import datetime, timezone
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import (
    HTTPRedirectHandler, Request, build_opener,
)

from django.db import transaction

from .dossier_versions import fork_dossier
from .models import (
    Evidence, Fact, FactDossier, ProductionJob, SourceReference,
)
from .wikidata import validate_wikidata_qid

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "FootballStudio/0.1 (https://github.com/whiteyOnTheMoon/FootballStudio)",
}
_API_WD = "https://www.wikidata.org/w/api.php"
_WD_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/"
_API_WP = "https://en.wikipedia.org/w/api.php"
_QID = re.compile(r"Q[1-9][0-9]{0,11}\Z")
_P31_FOOTBALL_CLUB = "Q476028"
_ALLOWED_WPM_HOSTS = {"www.wikidata.org", "en.wikipedia.org"}
_PREFIXES = {"sk", "fc", "fk", "sc", "sv", "afc", "cf", "ac", "sportklub", "football", "club"}
_NAME = re.compile(r"^[^<>\r\n\t]{2,160}$")


class AutoResearchError(ValueError):
    """Only stable codes. Never return untrusted API text."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_json(url, *, limit=256_000):
    """HTTPS fixed-host, bounded GET; reject all redirects and bad JSON."""
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https" or parsed.hostname not in _ALLOWED_WPM_HOSTS
        or parsed.username or parsed.password or parsed.port is not None
        or parsed.fragment
    ):
        raise AutoResearchError("invalid_endpoint")
    request = Request(url, headers=_HEADERS)
    try:
        with build_opener(_NoRedirect()).open(request, timeout=6) as response:
            data = response.read(limit + 1)
    except HTTPError as exc:
        raise AutoResearchError("service_busy" if exc.code in (429, 503) else "upstream_error") from None
    except (URLError, TimeoutError, OSError):
        raise AutoResearchError("network_error") from None
    if len(data) > limit:
        raise AutoResearchError("response_too_large")
    try:
        body = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise AutoResearchError("invalid_response") from None
    if not isinstance(body, dict) or "error" in body:
        raise AutoResearchError("invalid_response")
    return body


def _endpoint(base, **params):
    return base + "?" + urlencode({
        "format": "json", "maxlag": 5, **params,
    })


def _name(value):
    if type(value) is not str or not _NAME.fullmatch(value):
        raise AutoResearchError("invalid_club_name")
    tokens = re.findall(r"[^\W_]+", value.casefold())
    while len(tokens) > 1 and tokens[0] in _PREFIXES:
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1] in {"fc", "sc", "club"}:
        tokens.pop()
    return " ".join(tokens)


def _search_qids(name):
    result = _read_json(_endpoint(
        _API_WD, action="wbsearchentities", language="en", uselang="en",
        type="item", limit=7, search=name,
    ))
    rows = result.get("search")
    if not isinstance(rows, list) or len(rows) > 7:
        raise AutoResearchError("invalid_response")
    qids = []
    target = _name(name)
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        qid = row["id"]
        if not _QID.fullmatch(qid):
            continue
        labels = [row.get("label"), (row.get("match") or {}).get("text")
                  if isinstance(row.get("match"), dict) else None]
        if any(
            isinstance(v, str) and _NAME.fullmatch(v) and _name(v) == target
            for v in labels
        ):
            if qid not in qids:
                qids.append(qid)
    return qids[:3]


def _entity(qid):
    validate_wikidata_qid(qid)
    payload = _read_json(_WD_ENTITY + qid + ".json", limit=1_000_000)
    entities = payload.get("entities")
    entity = entities.get(qid) if isinstance(entities, dict) else None
    if not isinstance(entity, dict) or entity.get("id") != qid:
        raise AutoResearchError("invalid_entity")
    return entity


def _claims(entity, prop):
    claims = entity.get("claims")
    rows = claims.get(prop, []) if isinstance(claims, dict) else None
    if not isinstance(rows, list):
        raise AutoResearchError("invalid_entity")
    return [
        x for x in rows[:80]
        if isinstance(x, dict) and x.get("rank") in ("preferred", "normal")
        and isinstance(x.get("mainsnak"), dict)
        and x["mainsnak"].get("snaktype") == "value"
        and x["mainsnak"].get("property") == prop
    ]


def _statement_value(statement):
    payload = statement.get("mainsnak", {}).get("datavalue")
    return payload.get("value") if isinstance(payload, dict) else None


def _linked_ids(entity, prop):
    ids = []
    for statement in _claims(entity, prop):
        value = _statement_value(statement)
        if not isinstance(value, dict):
            continue
        qid = value.get("id")
        if isinstance(qid, str) and _QID.fullmatch(qid) and qid not in ids:
            ids.append(qid)
    return ids


def _iso_country(qid):
    data = _read_json(_endpoint(
        _API_WD, action="wbgetclaims", entity=qid, property="P297",
    ))
    claims = data.get("claims")
    rows = claims.get("P297") if isinstance(claims, dict) else None
    if not isinstance(rows, list) or len(rows) > 20:
        raise AutoResearchError("invalid_response")
    codes = []
    for row in rows:
        if not isinstance(row, dict) or row.get("rank") not in ("normal", "preferred"):
            continue
        value = _statement_value(row)
        if isinstance(value, str) and re.fullmatch(r"[A-Z]{2}", value):
            codes.append(value)
    return set(codes)


def _founding_year(entity):
    years = set()
    for stmt in _claims(entity, "P571"):
        value = _statement_value(stmt)
        if not isinstance(value, dict):
            continue
        stamp = value.get("time")
        precision = value.get("precision")
        if (
            not isinstance(stamp, str)
            or not re.fullmatch(r"\+[0-9]{4}-[0-9]{2}-[0-9]{2}T00:00:00Z", stamp)
            or type(precision) is not int or precision < 9
        ):
            continue
        year = int(stamp[1:5])
        if 1800 <= year <= datetime.now(timezone.utc).year:
            years.add(year)
    return next(iter(years)) if len(years) == 1 else None


def _wikipedia_title(entity):
    links = entity.get("sitelinks")
    link = links.get("enwiki") if isinstance(links, dict) else None
    title = link.get("title") if isinstance(link, dict) else None
    if (
        not isinstance(title, str) or not 2 <= len(title) <= 160
        or ":" in title or any(c in title for c in ("\r", "\n", "<", ">"))
    ):
        return None
    return title


def _wikipedia_intro(title):
    """Retrieve short plaintext intro for provenance; no HTML or article copy."""
    data = _read_json(_endpoint(
        _API_WP, action="query", prop="extracts", exintro="1",
        explaintext="1", titles=title, redirects="0",
    ), limit=64_000)
    query = data.get("query")
    pages = query.get("pages") if isinstance(query, dict) else None
    if not isinstance(pages, dict) or len(pages) != 1:
        raise AutoResearchError("invalid_response")
    page = next(iter(pages.values()))
    if (
        not isinstance(page, dict) or type(page.get("pageid")) is not int
        or page["pageid"] < 1 or page.get("ns") != 0
        or type(page.get("title")) is not str
        or page["title"].casefold() != title.casefold()
        or not isinstance(page.get("extract"), str)
    ):
        raise AutoResearchError("invalid_response")
    return page["extract"][:10_000]


def discover_free_club_research(*, club_name, country_code):
    """Bounded real Wikimedia research, never trusted reviewer certification.

    Strong auto-selection requires one matching name, P31 football-club
    instance and P17 country whose P297 ISO code matches the selected club.
    No Q-ID is hardcoded; ambiguous/no-country matches fail closed.
    """
    if not isinstance(country_code, str) or not re.fullmatch(r"[A-Z]{2}", country_code):
        raise AutoResearchError("invalid_country")
    qids = _search_qids(club_name)
    matches = []
    for qid in qids:
        entity = _entity(qid)
        if _P31_FOOTBALL_CLUB not in _linked_ids(entity, "P31"):
            continue
        countries = _linked_ids(entity, "P17")
        if not countries:
            continue
        if any(country_code in _iso_country(country) for country in countries[:2]):
            matches.append((qid, entity))
    if not matches:
        raise AutoResearchError("no_confident_match")
    if len(matches) > 1:
        raise AutoResearchError("ambiguous_entity")

    qid, entity = matches[0]
    year = _founding_year(entity)
    title = _wikipedia_title(entity)
    wiki_link = None
    wiki_year_mentioned = False
    if title is not None:
        try:
            intro = _wikipedia_intro(title)
        except AutoResearchError:
            # Wikipedia may be unavailable. Wikidata still produces an
            # unverified candidate; no false claim of having checked Wiki.
            pass
        else:
            from urllib.parse import quote
            wiki_link = "https://en.wikipedia.org/wiki/" + quote(
                title.replace(" ", "_"), safe="",
            )
            if year is not None:
                wiki_year_mentioned = bool(re.search(
                    r"(?i)\b(?:founded|established|formed)\b.{0,65}\b"
                    + str(year) + r"\b", intro,
                ))
    en = entity.get("labels", {}).get("en")
    label = en.get("value") if isinstance(en, dict) else None
    if not isinstance(label, str) or not 2 <= len(label) <= 250:
        label = club_name
    return {
        "qid": qid,
        "label": label,
        "wikidata_url": _WD_ENTITY + qid + ".json",
        "founded_year_candidate": year,
        "wikipedia_url": wiki_link,
        "wikipedia_intro_mentions_year": wiki_year_mentioned,
        "retrieved_at": datetime.now(timezone.utc),
    }


def _latest(job):
    return FactDossier.objects.filter(job=job).order_by("-version").first()


def _already_imported(dossier):
    return dossier is not None and dossier.sources.filter(
        source_kind=SourceReference.Kind.WIKIDATA,
        external_id__startswith="Q",
        title__startswith="[auto] ",
    ).exists()


def import_free_club_research(*, owner, job_id, expected_version):
    """Create a new dossier containing automatic candidate facts, no reviews.

    On a repeat, reuse an imported latest dossier without extra API calls.
    Check ownership and version before any remote call; serialize writes under
    the job row lock. One explicit trigger, at most 3 matching entity lookups.
    """
    owner_id = getattr(owner, "pk", None)
    if (
        type(owner_id) is not int or owner_id < 1
        or type(job_id) is not int or job_id < 1
        or type(expected_version) is not int or expected_version < 0
    ):
        raise AutoResearchError("invalid_request")
    job = ProductionJob.objects.select_related("club__league__country").filter(
        pk=job_id, owner_id=owner_id,
    ).first()
    if job is None:
        raise AutoResearchError("not_authorized")
    latest = _latest(job)
    actual = latest.version if latest is not None else 0
    if _already_imported(latest):
        return latest
    if expected_version != actual:
        raise AutoResearchError("stale_dossier")
    discovered = discover_free_club_research(
        club_name=job.club_name, country_code=job.country_code,
    )

    with transaction.atomic():
        locked = ProductionJob.objects.select_for_update().get(
            pk=job.pk, owner_id=owner_id,
        )
        latest = _latest(locked)
        if _already_imported(latest):
            return latest
        if (latest.version if latest is not None else 0) != expected_version:
            raise AutoResearchError("stale_dossier")
        dossier = fork_dossier(job=locked, previous=latest)
        source = dossier.sources.filter(
            source_kind=SourceReference.Kind.WIKIDATA,
            external_id=discovered["qid"],
            url=discovered["wikidata_url"],
        ).first()
        if source is None:
            source = SourceReference.objects.create(
                dossier=dossier,
                url=discovered["wikidata_url"],
                source_kind=SourceReference.Kind.WIKIDATA,
                title="[auto] " + discovered["label"][:243],
                external_id=discovered["qid"],
                retrieved_at=discovered["retrieved_at"],
                access_state=SourceReference.Access.ACCESSIBLE,
            )
        else:
            # Only the new dossier version is modified; earlier snapshots stay intact.
            source.title = "[auto] " + discovered["label"][:243]
            source.retrieved_at = discovered["retrieved_at"]
            source.access_state = SourceReference.Access.ACCESSIBLE
            source.save(update_fields=["title", "retrieved_at", "access_state"])
        wikipedia_source = None
        if discovered["wikipedia_url"]:
            wikipedia_source = dossier.sources.filter(
                source_kind=SourceReference.Kind.WIKIPEDIA,
                url=discovered["wikipedia_url"],
            ).first()
            if wikipedia_source is None:
                wikipedia_source = SourceReference.objects.create(
                    dossier=dossier,
                    url=discovered["wikipedia_url"],
                    source_kind=SourceReference.Kind.WIKIPEDIA,
                    title="English Wikipedia: " + discovered["label"][:225],
                    external_id=discovered["qid"],
                    retrieved_at=discovered["retrieved_at"],
                    access_state=SourceReference.Access.ACCESSIBLE,
                )
        year = discovered["founded_year_candidate"]
        if year is not None:
            fact = Fact.objects.create(
                dossier=dossier, predicate="founded_year", value=year,
                assertion_text=f"The club was founded in {year}.",
                verification_state=Fact.Verification.UNVERIFIED,
            )
            Evidence.objects.create(
                fact=fact, source=source, role=Evidence.Role.UNKNOWN,
                locator=f"Wikidata {discovered['qid']} · inception (P571)",
                summary=(
                    f"Wikidata P571 gives the year {year}. "
                    "Automatically imported, not independently verified."
                ),
            )
            if wikipedia_source is not None and discovered["wikipedia_intro_mentions_year"]:
                Evidence.objects.create(
                    fact=fact, source=wikipedia_source,
                    role=Evidence.Role.UNKNOWN,
                    locator=f"English Wikipedia article intro · {year}",
                    summary=(
                        f"Article introduction mentions foundation year {year}. "
                        "Automated text match only; editorial review required."
                    ),
                )
        return dossier
