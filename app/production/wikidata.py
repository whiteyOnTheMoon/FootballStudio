"""Small, opt-in, no-paid-API Wikidata lookup by explicit entity ID.

This is a source snapshot, not verified facts or Wikipedia article content.
No name matching or external URL input is accepted.
"""
from datetime import datetime, timezone
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .official_site_links import _homepage

_QID = re.compile(r"Q[1-9][0-9]{0,11}\Z")

_MAX_WEBSITE_CANDIDATES = 5
_MAX_WEBSITE_STATEMENTS = 100
_STATEMENT_ID = re.compile(r"Q[1-9][0-9]{0,11}\$[A-Za-z0-9-]{1,80}\Z")


def _official_website_candidates(entity, qid, source_url):
    """P856 is an *unverified claim*, never a verified official domain.

    This extracts HTTPS-only URLs for later manual identity confirmation.
    Candidate URLs are NEVER fetched in this module. No DNS security is
    implied: a later fetcher must separately enforce robots, DNS and SSRF.
    """
    claims = entity.get("claims", {})
    if not isinstance(claims, dict):
        raise WikidataLookupError("invalid_response")
    statements = claims.get("P856", [])
    if not isinstance(statements, list):
        raise WikidataLookupError("invalid_response")

    items = []
    for statement in statements[:_MAX_WEBSITE_STATEMENTS]:
        if not isinstance(statement, dict):
            continue
        rank = statement.get("rank", "normal")
        if rank not in ("preferred", "normal"):
            continue
        snak = statement.get("mainsnak")
        if not isinstance(snak, dict) or (
            snak.get("property") != "P856"
            or snak.get("snaktype") != "value"
            or snak.get("datatype") != "url"
        ):
            continue
        datavalue = snak.get("datavalue")
        if not isinstance(datavalue, dict) or datavalue.get("type") != "string":
            continue
        url = datavalue.get("value")
        if (not isinstance(url, str) or len(url) > 500 or not url
                or any(c.isspace() or ord(c) < 32 or c == "\\" for c in url)):
            continue
        try:
            normalized, _ = _homepage(url)
        except ValueError:
            continue

        statement_id = statement.get("id")
        if not isinstance(statement_id, str) or not _STATEMENT_ID.fullmatch(statement_id):
            statement_id = None
        items.append({
            "url": normalized,
            "wikidata_property": "P856",
            "statement_id": statement_id,
            "rank": rank,
            "source_url": source_url,
            "verification_state": "unverified",
        })

    # Prefer higher-ranked statements and deterministically deduplicate URLs.
    # Even 'preferred' can be historical: callers must inspect provenance.
    items.sort(key=lambda item: (item["rank"] != "preferred", item["url"]))
    unique = {}
    for item in items:
        unique.setdefault(item["url"], item)
        if len(unique) == _MAX_WEBSITE_CANDIDATES:
            break
    return list(unique.values())


_MAX_RESPONSE_BYTES = 1_000_000
_TIMEOUT_SECONDS = 8


class WikidataLookupError(Exception):
    """Non-sensitive, machine-readable failure reason for a lookup."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _english_value(entity, property_name):
    values = entity.get(property_name, {})
    if not isinstance(values, dict):
        raise WikidataLookupError("invalid_response")
    en = values.get("en")
    if en is None:
        return None
    if not isinstance(en, dict) or not isinstance(en.get("value"), str):
        raise WikidataLookupError("invalid_response")
    return en["value"] or None


def _wikipedia_link(entity):
    sitelinks = entity.get("sitelinks", {})
    if not isinstance(sitelinks, dict):
        raise WikidataLookupError("invalid_response")
    english = sitelinks.get("enwiki")
    if english is None:
        return None
    if not isinstance(english, dict) or not isinstance(english.get("title"), str):
        raise WikidataLookupError("invalid_response")
    title = english["title"].strip()
    if not title:
        return None
    return "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="")


def validate_wikidata_qid(qid):
    """Reject anything except an explicit Wikidata entity ID."""
    if not isinstance(qid, str) or not _QID.fullmatch(qid):
        raise ValueError("A valid Wikidata Q-ID is required (for example Q123).")
    return qid


def fetch_wikidata_profile(qid):
    """Return serializable English profile metadata from Wikidata's EntityData API.

    Explicit Q-IDs only. Network is called only when this function is invoked.
    Does not write to the database, cache or call any paid service.
    """
    validate_wikidata_qid(qid)

    entity_url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    request = Request(entity_url, headers={
        "Accept": "application/json",
        "User-Agent": "FootballStudio/0.1 (https://github.com/whiteyOnTheMoon/FootballStudio)",
    })
    try:
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise WikidataLookupError("not_found" if exc.code == 404 else "http_error") from None
    except (URLError, TimeoutError, OSError):
        raise WikidataLookupError("network_error") from None

    if len(raw) > _MAX_RESPONSE_BYTES:
        raise WikidataLookupError("response_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise WikidataLookupError("invalid_json") from None

    if not isinstance(payload, dict) or not isinstance(payload.get("entities"), dict):
        raise WikidataLookupError("invalid_response")
    entity = payload["entities"].get(qid)
    if not isinstance(entity, dict) or entity.get("id") != qid:
        raise WikidataLookupError("entity_missing")

    return {
        "provider": "wikidata",
        "entity_id": qid,
        "label_en": _english_value(entity, "labels"),
        "description_en": _english_value(entity, "descriptions"),
        "source_url": entity_url,
        "wikipedia_url_en": _wikipedia_link(entity),
        "official_website_candidates": _official_website_candidates(entity, qid, entity_url),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
