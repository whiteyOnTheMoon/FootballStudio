"""FS-014c: deterministic, source-traceable research outline for a club film.

This is an EDITORIAL RESEARCH MAP, not voiceover text, script clearance or
a completed documentary. It may show unverified fact candidates because
each entry is visibly labelled as such. The strict script-safety gates are
unchanged. No LLM, HTTP, user text rendering or paid API.
"""
import re


_STAGES = (
    ("origins", "Origins of the club", "0:00–1:00"),
    ("home", "A home and an identity", "1:00–2:00"),
    ("trophies", "Turning points and silverware", "2:00–6:30"),
    ("people", "People who shaped the club", "6:30–9:00"),
)
_HONOUR_NAMES = {
    "league_champion": "League championship",
    "domestic_cup": "Domestic cup",
}
_CORROBORATION = {
    "both": "Two official source domains agree",
    "league_only": "League listing; club profile does not list it",
    "club_only": "Club profile only; league listing lacks it",
    "club_not_checked": "League listing; club profile not checked",
}
_SEASON = re.compile(r"(?:19|20)[0-9]{2}/[0-9]{2}\Z")


def _tag(fact):
    return "reviewed" if (
        fact.get("verification_state") == "verified"
        and isinstance(fact.get("review"), dict)
        and fact["review"].get("decision") == "verified"
    ) else "unverified"


def _sources(fact, source_ids):
    return sorted({
        ref["source_id"]
        for ref in fact.get("evidence", [])
        if (
            isinstance(ref, dict)
            and type(ref.get("source_id")) is int
            and ref["source_id"] in source_ids
        )
    })


def _item(fact, text, source_ids):
    return {
        "fact_id": fact["id"],
        "label": text,
        "status": _tag(fact),
        "source_ids": _sources(fact, source_ids),
    }


def build_documentary_research_outline(snapshot):
    """Pure, limited outline from already saved structured dossier candidates.

    No new claims, no unsourced Wikipedia summary, no narration and no
    auto-verification. Intentionally returns <=10 rows per beat.
    """
    if (
        not isinstance(snapshot, dict)
        or not isinstance(snapshot.get("facts"), list)
        or not isinstance(snapshot.get("sources"), list)
    ):
        raise ValueError("Invalid research dossier.")
    source_ids = {
        item["id"] for item in snapshot["sources"]
        if isinstance(item, dict) and type(item.get("id")) is int
    }
    groups = {key: [] for key, _title, _time in _STAGES}
    for fact in snapshot["facts"]:
        if not isinstance(fact, dict) or type(fact.get("id")) is not int:
            continue
        predicate = fact.get("predicate")
        value = fact.get("value")
        label, section = None, None
        if (
            predicate == "founded_year" and type(value) is int
            and 1800 <= value <= 2100
        ):
            label, section = f"Foundation year candidate: {value}", "origins"
        elif (
            predicate == "stadium_name" and isinstance(value, str)
            and 2 <= len(value) <= 160
        ):
            label, section = f"Home stadium candidate: {value}", "home"
        elif predicate == "club_honour_candidate" and isinstance(value, dict):
            season = value.get("season")
            category = value.get("category")
            corroboration = value.get("corroboration")
            if (
                isinstance(season, str) and _SEASON.fullmatch(season)
                and category in _HONOUR_NAMES
                and corroboration in _CORROBORATION
            ):
                label, section = (
                    f"{season}: {_HONOUR_NAMES[category]} — "
                    f"{_CORROBORATION[corroboration]}"
                ), "trophies"
        elif predicate in (
            "official_player_legend_candidate",
            "official_coach_legend_candidate",
        ) and isinstance(value, dict):
            name = value.get("name")
            if isinstance(name, str) and 2 <= len(name) <= 120:
                role = (
                    "Player" if predicate == "official_player_legend_candidate"
                    else "Coach"
                )
                label, section = f"{role} on the club legends list: {name}", "people"
        if label is not None and section is not None:
            groups[section].append(_item(fact, label, source_ids))

    # The clearest historical story usually starts at the earliest trophy
    # years, while displaying only a bounded example set.
    groups["trophies"].sort(key=lambda v: v["label"])
    sections = [
        {
            "key": key, "title": title, "time_window": times,
            "candidate_count": len(groups[key]),
            "reviewed_count": sum(
                row["status"] == "reviewed" for row in groups[key]
            ),
            "items": groups[key][:10],
            "additional_count": max(0, len(groups[key]) - 10),
        }
        for key, title, times in _STAGES
    ]
    return {
        "sections": sections,
        "total_candidate_count": sum(
            section["candidate_count"] for section in sections
        ),
        "reviewed_count": sum(
            section["reviewed_count"] for section in sections
        ),
        "target_duration_minutes": 9,
        "ready_for_voiceover": False,
        "mode": "research_outline_only",
    }
