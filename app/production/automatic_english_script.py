"""FS-019: automatic, source-linked English documentary SCRIPT DRAFT.

This module is an explicitly limited editorial assembly stage, not a full
8–10 minute film or voiceover clearance. It never claims that an unverified
Wikidata or club statement is independently true; the language always
attributes the information to the original *record*. A record of agreement
between two official pages is still not independent proof of a football
result.

The only input is an owner-scoped, serialized immutable dossier snapshot.
There are no database writes, network requests, model calls or paid APIs.
Existing human-only script safety remains unchanged.

The editor can inspect this output, but the default film worker generates
it without any required source/fact clicks. The output is deliberately short
when source coverage is short; no invented history, no filler paragraphs.
"""
from collections import Counter
from datetime import datetime, timezone
import re

from .film_claim_assessment import assess_research_snapshot, _site_identity

_QID = re.compile(r"Q[1-9][0-9]{0,11}\Z")
_YEARS = re.compile(r"(?:19|20)[0-9]{2}/[0-9]{2}\Z")
_WD = "https://www.wikidata.org/wiki/Special:EntityData/"
_ROLE = ("unknown", "supports")
_MAX_FACTS = 250
_MAX_TITLES = 20
_MAX_LEGENDS = 8
_WORDS_PER_MINUTE = 145
_MIN_SCREENPLAY_WORDS = 1100
_MAX_SCREENPLAY_WORDS = 1550
_SECTIONS = (
    ("origins", "Origins and identity"),
    ("home", "A place to call home"),
    ("honours", "Seasons of silverware"),
    ("people", "The names the club remembers"),
)


def _safe_name(value, limit=160):
    return (
        type(value) is str
        and 2 <= len(value) <= limit
        and value == value.strip()
        and value.isprintable()
        and all(
            char.isalnum() or char in " .'-–’" for char in value
        )
        and any(char.isalpha() for char in value)
    )


def _valid_qid(value):
    return type(value) is str and _QID.fullmatch(value) is not None


def _club_qid(snapshot):
    qids = set()
    for row in snapshot["sources"]:
        if not isinstance(row, dict):
            continue
        qid = row.get("external_id")
        if (
            row.get("source_kind") == "wikidata"
            and _valid_qid(qid)
            and type(row.get("title")) is str
            and row["title"].startswith("[auto] ")
            and row.get("access_state") == "accessible"
            and row.get("url") == _WD + qid + ".json"
        ):
            qids.add(qid)
    return next(iter(qids)) if len(qids) == 1 else None


def _evidence(fact, source_by_id, *, source_id, locator):
    links = fact.get("evidence")
    return isinstance(links, list) and any(
        isinstance(link, dict)
        and link.get("source_id") == source_id
        and type(link.get("source_id")) is int
        and link.get("locator") == locator
        and link.get("role") in _ROLE
        and isinstance(source_by_id.get(source_id), dict)
        and source_by_id[source_id].get("access_state") == "accessible"
        for link in links
    )


def _no_conflict(fact):
    rows = fact.get("evidence")
    return (
        fact.get("verification_state") not in (
            "rejected", "conflicted", "insufficient_sources",
        )
        and isinstance(rows, list)
        and all(
            isinstance(row, dict) and row.get("role") != "contradicts"
            for row in rows
        )
    )


def _unique(facts, predicate, value_field=None):
    """Return a single unique *value*, or no candidate if values disagree."""
    matching = [f for f in facts if (
        f.get("predicate") == predicate and _no_conflict(f)
    )]
    values = [
        f.get("value") if value_field is None else (
            f.get("value", {}).get(value_field)
            if isinstance(f.get("value"), dict) else None
        ) for f in matching
    ]
    if not matching or any(value != values[0] for value in values):
        return []
    return matching


def _line(text, fact_id, source_ids, basis):
    return {
        "text": text,
        "fact_ids": [fact_id],
        "source_ids": sorted(set(source_ids)),
        "basis": basis,
        "approved_for_voiceover": False,
    }


def assemble_english_documentary_draft(snapshot, *, assessment=None):
    """Create an English, fact-linked preview, never a narration-ready script.

    No generic act receives filler text. When the dossier is too shallow,
    word count and duration reflect that honestly. Only narrow structured
    source observations are included; user assertion_text is never copied.
    """
    if (
        not isinstance(snapshot, dict)
        or not isinstance(snapshot.get("facts"), list)
        or not isinstance(snapshot.get("sources"), list)
    ):
        raise ValueError("A serialized owned research dossier is required.")
    # Never trust caller-supplied match classifications. A mismatched
    # or stale assessment must not enter the script, even in a preview.
    verified_assessment = assess_research_snapshot(snapshot)
    if assessment is not None and assessment != verified_assessment:
        raise ValueError("An assessment of this exact dossier is required.")
    assessment = verified_assessment

    facts = [
        row for row in snapshot["facts"][:_MAX_FACTS]
        if isinstance(row, dict) and type(row.get("id")) is int
        and row["id"] > 0
    ]
    fact_id_counts = Counter(row["id"] for row in facts)
    facts = [row for row in facts if fact_id_counts[row["id"]] == 1]
    source_id_counts = Counter(
        source["id"] for source in snapshot["sources"]
        if isinstance(source, dict)
        and type(source.get("id")) is int and source["id"] > 0
    )
    sources = {
        row["id"]: row for row in snapshot["sources"]
        if isinstance(row, dict)
        and type(row.get("id")) is int
        and source_id_counts[row["id"]] == 1
    }
    club = snapshot.get("club_name")
    qid = _club_qid(snapshot)
    groups = {key: [] for key, _title in _SECTIONS}

    # Never interpolate untrusted club names in English draft paragraphs.
    if not _safe_name(club):
        club = None

    if club is not None and qid is not None:
        source = next((
            row for row in sources.values()
            if row.get("source_kind") == "wikidata"
            and row.get("external_id") == qid
            and row.get("url") == _WD + qid + ".json"
            and row.get("access_state") == "accessible"
            and type(row.get("title")) is str
            and row["title"].startswith("[auto] ")
        ), None)
        if source is not None:
            founded = _unique(facts, "founded_year")
            if founded:
                fact = founded[0]
                year = fact.get("value")
                if (
                    type(year) is int and 1800 <= year <= datetime.now(timezone.utc).year
                    and _evidence(
                        fact, sources, source_id=source["id"],
                        locator=f"Wikidata {qid} · inception (P571)",
                    )
                ):
                    groups["origins"].append(_line(
                        f"The Wikidata entry for {club} records {year} as "
                        "its inception year. That record is a starting point "
                        "for the story, rather than independent confirmation "
                        "of the club's founding date.",
                        fact["id"], [source["id"]], "attributed_wikidata",
                    ))

            venues = _unique(facts, "stadium_name")
            if venues:
                fact = venues[0]
                venue = fact.get("value")
                if (
                    _safe_name(venue)
                    and _evidence(
                        fact, sources, source_id=source["id"],
                        locator=f"Wikidata {qid} · home venue (P115)",
                    )
                ):
                    # The exact linked venue entity is also saved by P115.
                    item_label = next((
                        link for link in fact["evidence"]
                        if isinstance(link, dict)
                        and type(link.get("source_id")) is int
                        and (linked := sources.get(link["source_id"])) is not None
                        and linked.get("source_kind") == "wikidata"
                        and _valid_qid(linked.get("external_id"))
                        and linked.get("url") == (
                            _WD + linked["external_id"] + ".json"
                        )
                        and linked.get("access_state") == "accessible"
                        and link.get("locator") == (
                            f"Wikidata item {linked['external_id']} · English label"
                        )
                        and link.get("role") in _ROLE
                    ), None)
                    if item_label is not None:
                        groups["home"].append(_line(
                            f"The same Wikidata record associates {club} "
                            f"with a home venue labelled {venue}. The linked "
                            "venue entry provides the name, but these records "
                            "do not by themselves establish the current "
                            "stadium's official status.",
                            fact["id"],
                            [source["id"], item_label["source_id"]],
                            "attributed_wikidata",
                        ))

    # Preserve the strict, separate source agreement assessment; do not
    # convert 'matched records' into a claim of independent historical truth.
    matches = {
        item["fact_id"]: item
        for item in assessment["items"]
        if isinstance(item, dict)
        and type(item.get("fact_id")) is int
        and item.get("status") == "matching_records"
        and isinstance(item.get("source_ids"), list)
        and len(item["source_ids"]) >= 2
    }
    honours = []
    for fact in facts:
        row = fact.get("value")
        if (
            fact.get("predicate") != "club_honour_candidate"
            or not _no_conflict(fact)
            or not isinstance(row, dict)
            or fact["id"] not in matches
        ):
            continue
        season, category = row.get("season"), row.get("category")
        if (
            type(season) is str and _YEARS.fullmatch(season)
            and category in ("domestic_cup", "league_champion")
            and row.get("corroboration") == "both"
        ):
            honours.append((season, category, fact["id"]))
    for season, category, fid in sorted(honours)[:_MAX_TITLES] if club else ():
        title = (
            "domestic cup" if category == "domestic_cup"
            else "league championship"
        )
        matched = matches[fid]
        groups["honours"].append(_line(
            f"For the {season} season, the recorded official league "
            f"winners list and the club's own published honours profile "
            f"both list {club} as {title} winners. Their entries agree "
            "on this season; that agreement is not an independent "
            "historical investigation.",
            fid, matched["source_ids"], "matching_official_lists",
        ))

    # The official legends parser uses a bounded club-site extraction. It
    # shows what *the website lists*; it does not independently establish
    # a person's entire career or that any person is universally a legend.
    people = []
    for fact in facts:
        if fact.get("predicate") not in (
            "official_player_legend_candidate",
            "official_coach_legend_candidate",
        ) or not _no_conflict(fact):
            continue
        value = fact.get("value")
        if (
            qid is None or not isinstance(value, dict)
            or value.get("club_qid") != qid
            or not _safe_name(value.get("name"), limit=120)
        ):
            continue
        is_player = fact["predicate"] == "official_player_legend_candidate"
        expected_basis = (
            "exact_name_on_confirmed_official_club_list" if is_player
            else "name_on_confirmed_official_club_list"
        )
        locator = (
            "Official club legend roster · player section" if is_player
            else "Official club legend roster · coaching section"
        )
        if value.get("match_basis") != expected_basis:
            continue
        linked = [
            source["id"] for source in sources.values()
            if source.get("source_kind") == "club_official"
            and source.get("external_id") == "auto-official-legends:" + qid
            and source.get("access_state") == "accessible"
            and _site_identity(source.get("url")) is not None
            and _evidence(
                fact, sources, source_id=source["id"], locator=locator,
            )
        ]
        if len(linked) != 1:
            continue
        people.append((value["name"], "player" if is_player else "coach",
                       fact["id"], linked[0]))
    for name, role, fid, sid in sorted(people)[:_MAX_LEGENDS] if club else ():
        groups["people"].append(_line(
            f"On its published {role}-legends list, the club names "
            f"{name}. This is a record of the club's own recognition, "
            "not a claim that every part of the person's football "
            "career has been independently checked.",
            fid, [sid], "attributed_official_roster",
        ))

    sections = [{
        "key": key, "heading": title, "paragraphs": groups[key],
        "paragraph_count": len(groups[key]),
    } for key, title in _SECTIONS]
    paragraphs = [line for section in sections for line in section["paragraphs"]]
    count = sum(len(line["text"].split()) for line in paragraphs)
    citations = sorted({sid for line in paragraphs for sid in line["source_ids"]})
    return {
        "mode": "automatic_source_attributed_script_draft",
        "dossier_version": snapshot.get("version"),
        "language": "en",
        "target_duration_minutes": 9,
        "estimated_duration_minutes": round(count / _WORDS_PER_MINUTE, 2),
        "word_count": count,
        "target_min_words": _MIN_SCREENPLAY_WORDS,
        "target_max_words": _MAX_SCREENPLAY_WORDS,
        "section_count": len(sections),
        "paragraph_count": len(paragraphs),
        "referenced_source_ids": citations,
        "sections": sections,
        "has_enough_material": _MIN_SCREENPLAY_WORDS <= count <= _MAX_SCREENPLAY_WORDS,
        "quality_gate": (
            "insufficient_source_material"
            if count < _MIN_SCREENPLAY_WORDS
            else "excess_material"
            if count > _MAX_SCREENPLAY_WORDS
            else "pending_independent_quality_review"
        ),
        "approved_for_voiceover": False,
    }
