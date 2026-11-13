"""FS-018: conservative, automatic source-agreement assessment.

The result is a machine-generated RESEARCH report, not a human FactReview,
verification_state change, safe_script_preview permission or voiceover script.
It makes no HTTP requests. Only the saved, structured official honours
parser output is currently eligible for a two-context match.

Neither two websites nor two HTTP fetches establish independent truth.
The report says only that two recorded source contexts agree on a season;
future narrative production needs additional validation and editorial rules.
"""
from datetime import datetime, timezone
import ipaddress
import re
from urllib.parse import urlsplit

_SEASON = re.compile(r"(19|20)[0-9]{2}/[0-9]{2}\Z")
_QID = re.compile(r"Q[1-9][0-9]{0,11}\Z")
_NAME = re.compile(r"^[^<>\r\n\t]{2,160}\Z")
_TITLE_CATEGORIES = {
    "league_champion": ("league championship", "Meister"),
    "domestic_cup": ("domestic cup", "Cup-Sieger"),
}
_STATUSES = (
    "matching_records", "listing_difference", "single_source",
    "not_evaluated", "conflict", "excluded",
)
_LIMIT = 250


def _good_season(season):
    return (
        type(season) is str
        and _SEASON.fullmatch(season) is not None
        and 1900 <= int(season[:4]) <= datetime.now(timezone.utc).year
        and int(season[-2:]) == (int(season[:4]) + 1) % 100
    )


def _site_identity(url):
    """Pure URL parsing, not an assertion that a domain is actually owned.

    This never resolves DNS and never accesses these sites. Reject potentially
    ambiguous URL forms and identical registrable-domain lookalikes.
    """
    if not isinstance(url, str) or len(url) > 750:
        return None
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https" or not host
        or parsed.username is not None or parsed.password is not None
        or port is not None or parsed.query or parsed.fragment
        or (parsed.path and not parsed.path.startswith("/"))
        or any(ch.isspace() for ch in url)
    ):
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    if not host or not re.fullmatch(r"[a-z0-9.-]+", host):
        return None
    parts = host.split(".")
    if len(parts) < 2 or any(not part or part.startswith("-") or part.endswith("-") for part in parts):
        return None
    # Conservative organizational grouping for common two-letter country TLDs.
    take = 3 if (
        len(parts) >= 3 and len(parts[-1]) == 2
        and parts[-2] in ("co", "com", "org", "net", "gov", "ac")
    ) else 2
    return ".".join(parts[-take:])


def _valid_source(source, kind, prefix):
    return (
        isinstance(source, dict)
        and type(source.get("id")) is int
        and source["id"] > 0
        and source.get("source_kind") == kind
        and source.get("access_state") == "accessible"
        and type(source.get("external_id")) is str
        and source["external_id"].startswith(prefix)
        and _QID.fullmatch(source["external_id"][len(prefix):]) is not None
        and _site_identity(source.get("url")) is not None
    )


def _autohonour_source_pairs(sources):
    league = {}
    club = {}
    for source in sources:
        if _valid_source(source, "league_official", "auto-honours:"):
            qid = source["external_id"][len("auto-honours:"):]
            league[source["id"]] = (qid, _site_identity(source["url"]))
        if _valid_source(source, "club_official", "auto-honours-club:"):
            qid = source["external_id"][len("auto-honours-club:"):]
            club[source["id"]] = (qid, _site_identity(source["url"]))
    return league, club


def _evidence_role_conflict(fact):
    rows = fact.get("evidence")
    return isinstance(rows, list) and any(
        isinstance(row, dict) and row.get("role") == "contradicts"
        for row in rows
    )


def _source_ids_for_title(fact, sources_by_id, season, category):
    """Return only exact season/category locators from the two official parsers."""
    league, club = set(), set()
    markers = {
        "league_official": f"Season {season} · {_TITLE_CATEGORIES[category][1]}",
        "club_official": f"National success · {season} · {category}",
    }
    links = fact.get("evidence")
    for link in links if isinstance(links, list) else ():
        if not isinstance(link, dict) or link.get("role") not in ("unknown", "supports"):
            continue
        sid = link.get("source_id")
        if type(sid) is not int:
            continue
        source = sources_by_id.get(sid)
        if not isinstance(source, dict):
            continue
        kind = source.get("source_kind")
        if link.get("locator") != markers.get(kind):
            continue
        if kind == "league_official" and _valid_source(
            source, kind, "auto-honours:"
        ):
            league.add(sid)
        if kind == "club_official" and _valid_source(
            source, kind, "auto-honours-club:"
        ):
            club.add(sid)
    return league, club


def assess_research_snapshot(snapshot):
    """Produce a bounded, fail-closed, human-review-free source report."""
    if (
        not isinstance(snapshot, dict)
        or not isinstance(snapshot.get("sources"), list)
        or not isinstance(snapshot.get("facts"), list)
    ):
        raise ValueError("A serialized research dossier is required.")

    sources = {
        source["id"]: source
        for source in snapshot["sources"]
        if isinstance(source, dict)
        and type(source.get("id")) is int and source["id"] > 0
    }
    league_sources, club_sources = _autohonour_source_pairs(sources.values())
    counts = {key: 0 for key in _STATUSES}
    items = []

    for fact in snapshot["facts"][:_LIMIT]:
        if not isinstance(fact, dict) or type(fact.get("id")) is not int:
            continue
        status = "not_evaluated"
        reason = "unsupported_fact_type_or_insufficient_structure"
        candidate = None
        source_ids = []

        if fact.get("verification_state") == "rejected":
            status, reason = "excluded", "manually_rejected"
        elif (
            fact.get("verification_state") == "conflicted"
            or _evidence_role_conflict(fact)
        ):
            status, reason = "conflict", "explicit_conflict"
        elif fact.get("predicate") == "club_honour_candidate":
            value = fact.get("value")
            if isinstance(value, dict):
                season = value.get("season")
                category = value.get("category")
                record_status = value.get("corroboration")
                if (
                    _good_season(season)
                    and type(category) is str and category in _TITLE_CATEGORIES
                    and type(record_status) is str
                ):
                    ids_league, ids_club = _source_ids_for_title(
                        fact, sources, season, category,
                    )
                    leagues = {
                        league_sources[sid] for sid in ids_league
                        if sid in league_sources
                    }
                    clubs = {
                        club_sources[sid] for sid in ids_club
                        if sid in club_sources
                    }
                    matched = any(
                        same_qid == other_qid and league_domain != club_domain
                        for same_qid, league_domain in leagues
                        for other_qid, club_domain in clubs
                    )
                    if record_status == "both" and matched:
                        status, reason = (
                            "matching_records", "two_distinct_official_source_contexts"
                        )
                        source_ids = sorted(ids_league | ids_club)
                        name = snapshot.get("club_name")
                        if type(name) is str and _NAME.fullmatch(name):
                            # This is a research sentence, NOT approved narration.
                            title = _TITLE_CATEGORIES[category][0]
                            candidate = (
                                f"Both the recorded league and club sources list "
                                f"{name} as {title} winners for {season}."
                            )
                    elif record_status in ("league_only", "club_only"):
                        # A missing entry in a second published list is only
                        # a documented listing difference if that second
                        # official page was actually fetched and saved.
                        all_league = set(league_sources.values())
                        all_club = set(club_sources.values())
                        first, other = (
                            (leagues, all_club) if record_status == "league_only"
                            else (clubs, all_league)
                        )
                        both_contexts = any(
                            qid_a == qid_b and root_a != root_b
                            for qid_a, root_a in first
                            for qid_b, root_b in other
                        )
                        if first and both_contexts:
                            status, reason = (
                                "listing_difference", "source_lists_not_aligned"
                            )
                            source_ids = sorted(ids_league | ids_club)
                        elif first:
                            status, reason = "single_source", "second_profile_not_available"
                            source_ids = sorted(ids_league | ids_club)
                    elif record_status == "club_not_checked" and leagues:
                        status, reason = "single_source", "club_profile_not_checked"
                        source_ids = sorted(ids_league | ids_club)
                    else:
                        status, reason = "not_evaluated", "no_valid_source_pair"

        counts[status] += 1
        items.append({
            "fact_id": fact["id"],
            "predicate": fact.get("predicate") if type(fact.get("predicate")) is str else "",
            "status": status,
            "reason": reason,
            "source_ids": source_ids,
            "research_sentence": candidate,
            "human_verified": (
                fact.get("verification_state") == "verified"
                and isinstance(fact.get("review"), dict)
                and fact["review"].get("decision") == "verified"
            ),
        })

    return {
        "mode": "machine_source_assessment_only",
        "dossier_version": snapshot.get("version"),
        "total_facts_evaluated": len(items),
        "additional_facts_not_evaluated": max(
            0, len(snapshot["facts"]) - _LIMIT
        ),
        "counts": counts,
        "items": items,
        "approved_for_voiceover": False,
        "no_human_reviews_created": True,
    }
