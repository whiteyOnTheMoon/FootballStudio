"""FS-014c: one-click, resumable research planning for one owned club.

The POST endpoint executes *at most one* already guarded import step per HTTP
request. Browser JS can chain successive POSTs after one explicit user click.
Each step independently re-checks owner, dossier version, source consent,
robots.txt and upstream bounds in the existing import services.

No new consent is inferred from Wikimedia or club catalogue data. This
orchestrator never marks facts verified or starts audio/video production.
"""
import re

from .models import FactDossier, SourceReference
from .official_site_preflight import plan_confirmed_official_source
from .wikimedia_auto import AutoResearchError


STEP_ORDER = (
    ("club", "Verein eindeutig zuordnen", "Wikidata / Wikipedia"),
    ("stadium", "Stadion recherchieren", "Wikidata P115"),
    ("players", "Spieler der Vereinsgeschichte finden", "Wikidata P54"),
    ("legends", "Offizielle Vereinslegenden abgleichen", "bestätigte Vereinswebsite"),
    ("honours", "Titelchronik und Quellenvergleich", "bestätigte Ligawebsite"),
)
_QID = re.compile(r"Q[1-9][0-9]{0,11}\Z")

# No new or user-controlled endpoints: each importer remains authoritative.
_IMPORTERS = {
    "club": ("wikimedia_auto", "import_free_club_research"),
    "stadium": ("wikimedia_stadium", "enrich_wikimedia_stadium"),
    "players": ("wikimedia_players", "import_wikidata_player_candidates"),
    "legends": ("official_legends", "crosscheck_official_club_legends"),
    "honours": ("official_honours", "import_official_honours_timeline"),
}


def _auto_club(dossier):
    if dossier is None:
        return None
    rows = list(dossier.sources.filter(
        source_kind=SourceReference.Kind.WIKIDATA,
        title__startswith="[auto] ",
        external_id__regex=r"^Q[1-9][0-9]{0,11}$",
    ).order_by("pk")[:2])
    if len(rows) != 1:
        return None
    row = rows[0]
    qid = row.external_id
    if not _QID.fullmatch(qid):
        return None
    return qid if row.url == (
        f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    ) else None


def _has_confirmed(dossier, owner_id, kind):
    if dossier is None:
        return False
    for source in dossier.sources.filter(source_kind=kind).order_by("pk")[:10]:
        if plan_confirmed_official_source(
            source, owner_id=owner_id, current_dossier_id=dossier.pk,
        ) is not None:
            return True
    return False


def research_plan(*, job, dossier=None):
    """Read-only plan, no network requests and no database mutation.

    Each step can be 'completed', 'ready', 'waiting', or 'requires_source'.
    Unavailable source permissions are skipped for selection, not bypassed;
    no hidden approval is created. A 'completed' stage records a successful
    research import, NOT independent fact verification.
    """
    if dossier is not None and (
        not isinstance(dossier, FactDossier) or dossier.job_id != job.pk
    ):
        raise ValueError("The research dossier does not belong to this job.")
    qid = _auto_club(dossier)
    has_club = bool(qid)
    has_stadium = bool(
        dossier is not None and dossier.facts.filter(
            predicate="stadium_name",
        ).exists()
    )
    has_players = bool(
        has_club and dossier.sources.filter(
            source_kind=SourceReference.Kind.WIKIDATA,
            external_id="auto-p54:" + qid,
        ).exists()
    )
    has_legends = bool(
        has_club and dossier.sources.filter(
            source_kind=SourceReference.Kind.CLUB_OFFICIAL,
            external_id="auto-official-legends:" + qid,
        ).exists()
    )
    has_honours = bool(
        has_club and dossier.sources.filter(
            source_kind=SourceReference.Kind.LEAGUE_OFFICIAL,
            external_id="auto-honours:" + qid,
        ).exists()
    )
    can_club = _has_confirmed(
        dossier, job.owner_id, SourceReference.Kind.CLUB_OFFICIAL,
    )
    can_league = _has_confirmed(
        dossier, job.owner_id, SourceReference.Kind.LEAGUE_OFFICIAL,
    )
    status = {
        "club": "completed" if has_club else "ready",
        "stadium": (
            "completed" if has_stadium else "ready" if has_club else "waiting"
        ),
        "players": (
            "completed" if has_players else "ready" if has_club else "waiting"
        ),
        "legends": (
            "completed" if has_legends
            else "waiting" if not has_players
            else "ready" if can_club
            else "requires_source"
        ),
        "honours": (
            "completed" if has_honours
            else "waiting" if not has_club
            else "ready" if can_league
            else "requires_source"
        ),
    }
    steps = [
        {
            "id": key, "title": label, "source": source,
            "status": status[key],
        }
        for key, label, source in STEP_ORDER
    ]
    next_id = next(
        (s["id"] for s in steps if s["status"] == "ready"), None,
    )
    completed = sum(item["status"] == "completed" for item in steps)
    return {
        "steps": steps,
        "next_id": next_id,
        "completed": completed,
        "total": len(steps),
        "complete": completed == len(steps),
        "requires_source": any(
            step["status"] == "requires_source" for step in steps
        ),
        "version": dossier.version if dossier is not None else 0,
    }


def execute_next_research(*, owner, job, expected_version):
    """Execute only the next planned step, with no cross-step DB transaction.

    Each existing importer locks ProductionJob and versions its own dossier.
    A failure in one step does not roll back any *prior* successful stages,
    and no automated retry occurs on network/robots/identity errors.
    """
    owner_id = getattr(owner, "pk", None)
    if (
        type(owner_id) is not int or owner_id <= 0
        or type(expected_version) is not int or expected_version < 0
        or getattr(job, "owner_id", None) != owner_id
    ):
        raise AutoResearchError("not_authorized")
    latest = FactDossier.objects.filter(
        job_id=job.pk, job__owner_id=owner_id,
    ).order_by("-version").first()
    actual = latest.version if latest is not None else 0
    if expected_version != actual:
        raise AutoResearchError("stale_dossier")
    plan = research_plan(job=job, dossier=latest)
    stage = plan["next_id"]
    if stage is None:
        return {"stage": None, "dossier": latest, "plan": plan}

    # Local imports avoid new network permissions; all stage-specific guards
    # remain in those modules and run before their respective remote calls.
    from importlib import import_module
    module_name, function_name = _IMPORTERS[stage]
    importer = getattr(
        import_module("app.production." + module_name),
        function_name,
    )
    dossier = importer(
        owner=owner, job_id=job.pk, expected_version=expected_version,
    )
    return {
        "stage": stage,
        "dossier": dossier,
        "plan": research_plan(job=job, dossier=dossier),
    }
