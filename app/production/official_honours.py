"""FS-014b: club honours chronicle from official league + club sources.

One owner-only action reads a confirmed league champion table; a confirmed
club profile may independently corroborate seasons. Every candidate remains
UNVERIFIED even if two official domains agree. An absent club-profile season
is labelled "not corroborated", never asserted to be a false championship.

Transport uses the existing pinned public-IP HTTPS, robots, no redirects and
user-confirmed source permissions. No user-supplied URL or paid API.
"""
from datetime import timedelta
from html.parser import HTMLParser
import re
import time
import unicodedata
from urllib.parse import urljoin, urlsplit

from django.db import transaction
from django.utils import timezone

from .dossier_versions import fork_dossier
from .models import (
    Evidence, Fact, FactDossier, ProductionJob, SourceReference,
)
from .official_site_preflight import plan_confirmed_official_source
from .official_site_research import _robots_policy
from .safe_official_fetch import (
    WebsiteFetchError, _checked_url, _download_public_https, _USER_AGENT,
)
from .wikimedia_auto import AutoResearchError


# Pilot discovery hints only: no fixed champions/club names/results.
# Neither hint bypasses an existing source confirmation or robots.txt.
_CLUB_PROFILE_PATHS = {
    ("Q124007617", "sksturm.at"): "/en/c/steckbrief",
}
_LEAGUE_HONOURS_PATHS = {
    ("AT", "www.bundesliga.at"): "/de/titel-uebersicht",
}
_SEASON = re.compile(r"(?:19|20)[0-9]{2}/[0-9]{2}\Z")
_CLUB_SEASONS = re.compile(r"(?:19|20)[0-9]{2}/[0-9]{2}")
_MAX_ROWS = 160
_MAX_WINNERS = 32
_MAX_HTML = 300_000
_HONOURS_MARKER = "auto-honours:"
_TITLE_TYPES = {
    "league_champion": "national league champion",
    "domestic_cup": "national cup winner",
}


def _fold(value):
    return " ".join(re.findall(
        r"[^\W_]+", unicodedata.normalize("NFKC", value.casefold()),
    )) if isinstance(value, str) else ""


def _season_valid(value):
    if type(value) is not str or not _SEASON.fullmatch(value):
        return False
    start = int(value[:4])
    finish = int(value[-2:])
    return 1900 <= start <= timezone.now().year and finish == (start + 1) % 100


def _team_matches(cell, selected_club):
    """Conservative suffix match allows historic sponsor/team prefixes.

    'SK Puntigamer Sturm Graz' matches selected 'Sturm Graz', but 'Sturm
    Graz II' and 'Sturm Graz Frauen' do not. Never broad substring matching.
    """
    target = _fold(selected_club)
    actual = _fold(cell)
    return bool(target and (
        actual == target or actual.endswith(" " + target)
    ))


class _TableRows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.depth = 0
        self.rows = []
        self.cells = None
        self.cell = None
        self.cell_kind = ""

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.rows = []
        elif self.depth == 1 and tag == "tr":
            self.cells = []
        elif self.depth == 1 and tag in ("th", "td") and self.cells is not None:
            self.cell, self.cell_kind = [], tag

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data[:300])

    def handle_endtag(self, tag):
        if self.depth == 1 and tag in ("th", "td") and self.cell is not None:
            value = " ".join(" ".join(self.cell).split())[:240]
            self.cells.append((self.cell_kind, value))
            self.cell = None
        elif self.depth == 1 and tag == "tr" and self.cells is not None:
            if len(self.rows) < _MAX_ROWS:
                self.rows.append(self.cells)
            self.cells = None
        elif tag == "table" and self.depth:
            self.depth -= 1
            if self.depth == 0:
                if len(self.tables) < 20:
                    self.tables.append(self.rows)
                self.rows = []


def _parse_league_table(html, club_name):
    """Read only explicit season/Meister/Cup-Sieger columns of a real table."""
    if type(html) is not str or not 20 <= len(html) <= _MAX_HTML:
        raise AutoResearchError("invalid_honours_page")
    parser = _TableRows()
    parser.feed(html)
    found = []
    for rows in parser.tables:
        for index, row in enumerate(rows):
            labels = [_fold(v).replace(" ", "") for _k, v in row]
            if not all(key in labels for key in ("saison", "meister", "cupsieger")):
                continue
            positions = {
                "season": labels.index("saison"),
                "league_champion": labels.index("meister"),
                "domestic_cup": labels.index("cupsieger"),
            }
            max_pos = max(positions.values())
            seasons = {}
            for item in rows[index + 1:]:
                if len(item) <= max_pos:
                    continue
                season = item[positions["season"]][1]
                if not _season_valid(season):
                    continue
                values = {
                    kind: item[pos][1] for kind, pos in positions.items()
                    if kind != "season"
                }
                if season in seasons and seasons[season] != values:
                    raise AutoResearchError("ambiguous_honours_table")
                seasons[season] = values
            if len(seasons) >= 10:
                found.append(seasons)
    if len(found) != 1:
        raise AutoResearchError("invalid_honours_table")
    wins = set()
    for season, values in found[0].items():
        for kind, team in values.items():
            if _team_matches(team, club_name):
                wins.add((season, kind))
    if not wins:
        raise AutoResearchError("no_honours_found")
    if len(wins) > _MAX_WINNERS:
        raise AutoResearchError("too_many_honours")
    return wins


class _ClubHonours(HTMLParser):
    """Read explicit 'National success' lines, not article-wide mentions."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = []
        self.in_heading = None
        self.heading = []
        self.in_national = False
        self.words = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template", "svg"):
            self.skip.append(tag)
            return
        if self.skip:
            return
        if tag in ("h2", "h3", "h4"):
            self.in_heading = tag
            self.heading = []

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_heading:
            self.heading.append(data[:180])
        elif self.in_national:
            self.words.append(data[:1000])

    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip[-1]:
                self.skip.pop()
            return
        if tag == self.in_heading:
            label = _fold(" ".join(self.heading))
            self.in_national = label in (
                "national success", "nationale erfolge",
                "nationale titel", "nationale erfolge und titel",
            )
            self.in_heading = None
            self.heading = []


def _parse_club_profile(html):
    """Parse bounded, explicitly counted Austrian champion/cup season lists."""
    if type(html) is not str or not 20 <= len(html) <= _MAX_HTML:
        raise AutoResearchError("invalid_club_profile")
    parser = _ClubHonours()
    parser.feed(html)
    prose = " ".join(parser.words)
    patterns = {
        "league_champion": r"Austrian Champion:\s*([0-9]{1,2})x\s*\(([^)]{1,250})\)",
        "domestic_cup": r"Austrian Cup Winner:\s*([0-9]{1,2})x\s*\(([^)]{1,250})\)",
    }
    result = set()
    for category, pattern in patterns.items():
        matches = list(re.finditer(pattern, prose, flags=re.I))
        if len(matches) != 1:
            raise AutoResearchError("invalid_club_profile")
        declared = int(matches[0].group(1))
        seasons = _CLUB_SEASONS.findall(matches[0].group(2))
        if len(seasons) != declared or len(set(seasons)) != declared:
            raise AutoResearchError("invalid_club_profile")
        for season in seasons:
            if not _season_valid(season):
                raise AutoResearchError("invalid_club_profile")
            result.add((season, category))
    return result


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = None
        self.words = []
        self.options = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            data = dict(attrs)
            if isinstance(data.get("href"), str):
                if "nofollow" not in (data.get("rel") or "").lower().split():
                    self.active, self.words = data["href"], [data.get("title") or ""]

    def handle_data(self, data):
        if self.active is not None:
            self.words.append(data[:140])

    def handle_endtag(self, tag):
        if tag == "a" and self.active is not None:
            self.options.append((self.active, " ".join(self.words)))
            self.active, self.words = None, []


def _find_one_page(homepage, html, *, role):
    parser = _Links()
    parser.feed(html)
    canonical, host = _checked_url(homepage)
    options = set()
    tokens = (
        ("steckbrief", "profile", "honours", "erfolge")
        if role == "club" else
        ("titel ubersicht", "titeltrager", "titles", "champions", "cups")
    )
    for href, label in parser.options[:200]:
        normalized_label = _fold(href + " " + label).replace("ü", "u")
        if not any(token in normalized_label for token in tokens):
            continue
        try:
            url, target_host = _checked_url(urljoin(canonical, href))
        except (ValueError, WebsiteFetchError):
            continue
        if target_host == host and url != canonical:
            options.add(url)
    if len(options) != 1:
        raise AutoResearchError("no_unique_honours_link")
    return next(iter(options))


def _official_sources(dossier, owner_id):
    eligible = {}
    for kind, expected in (
        (SourceReference.Kind.CLUB_OFFICIAL, "club"),
        (SourceReference.Kind.LEAGUE_OFFICIAL, "league"),
    ):
        plans = []
        for src in dossier.sources.filter(source_kind=kind).order_by("pk")[:8]:
            plan = plan_confirmed_official_source(
                src, owner_id=owner_id, current_dossier_id=dossier.pk,
            )
            if plan is not None and plan.context == expected:
                plans.append(plan)
        if len(plans) > 1:
            raise AutoResearchError("ambiguous_official_source")
        eligible[expected] = plans[0] if plans else None
    if eligible["league"] is None:
        raise AutoResearchError("no_confirmed_league_source")
    return eligible


def _club_qid(dossier):
    rows = list(dossier.sources.filter(
        source_kind=SourceReference.Kind.WIKIDATA,
        title__startswith="[auto] ",
        external_id__regex=r"^Q[1-9][0-9]{0,11}$",
    )[:2])
    if len(rows) != 1:
        raise AutoResearchError("no_auto_research")
    qid = rows[0].external_id
    if rows[0].url != (
        f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    ):
        raise AutoResearchError("invalid_club_source")
    return qid


def _read_official(homepage, *, role, hint=None, deadline):
    """No crawlers, up to one origin homepage and one approved detail page."""
    normalized, host = _checked_url(homepage)
    _robots_url, robots, delay = _robots_policy(normalized)
    if hint is not None:
        url = f"https://{host}{hint}"
    else:
        if not robots.can_fetch(_USER_AGENT, normalized):
            raise WebsiteFetchError("robots_disallowed")
        if time.monotonic() + delay + 5 >= deadline:
            raise WebsiteFetchError("research_deadline")
        time.sleep(delay)
        intro = _download_public_https(normalized, kind="html")
        url = _find_one_page(normalized, intro, role=role)
    page_url, target = _checked_url(url)
    if target != host:
        raise WebsiteFetchError("unsafe_url")
    if not robots.can_fetch(_USER_AGENT, page_url):
        raise WebsiteFetchError("robots_disallowed")
    if time.monotonic() + delay + 5 >= deadline:
        raise WebsiteFetchError("research_deadline")
    time.sleep(delay)
    return page_url, _download_public_https(page_url, kind="html")


def _gather_honours(*, confirmed, club_qid, club_name, country_code):
    """Fetch league table, optionally independent club profile; bounded."""
    deadline = time.monotonic() + 45
    league_plan = confirmed["league"]
    league_host = league_plan.domain
    league_hint = _LEAGUE_HONOURS_PATHS.get((country_code, league_host))
    try:
        league_url, league_html = _read_official(
            league_plan.source_url, role="league",
            hint=league_hint, deadline=deadline,
        )
    except WebsiteFetchError as exc:
        raise AutoResearchError("league_site_" + exc.code) from None
    league_wins = _parse_league_table(league_html, club_name)

    club_profile = None
    club_url = None
    club_plan = confirmed["club"]
    if club_plan is not None:
        hint = _CLUB_PROFILE_PATHS.get((club_qid, club_plan.domain))
        try:
            club_url, club_html = _read_official(
                club_plan.source_url, role="club",
                hint=hint, deadline=deadline,
            )
            club_profile = _parse_club_profile(club_html)
        except (WebsiteFetchError, AutoResearchError):
            # Missing or robots-blocked independent page does NOT become
            # "club disagrees" or fabricate a second source.
            club_url = None
            club_profile = None
    return {
        "league_url": league_url,
        "club_url": club_url,
        "league_wins": league_wins,
        "club_wins": club_profile,
        "retrieved_at": timezone.now(),
    }


def _already_imported(dossier, club_qid):
    return dossier.sources.filter(
        source_kind=SourceReference.Kind.LEAGUE_OFFICIAL,
        external_id=_HONOURS_MARKER + club_qid,
    ).exists()


def import_official_honours_timeline(*, owner, job_id, expected_version):
    """One explicit click: copy historical snapshot + source-linked honours."""
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
    latest = FactDossier.objects.filter(job=job).order_by("-version").first()
    if latest is None:
        raise AutoResearchError("no_auto_research")
    qid = _club_qid(latest)
    if _already_imported(latest, qid):
        return latest
    if latest.version != expected_version:
        raise AutoResearchError("stale_dossier")
    plans = _official_sources(latest, owner_id)
    result = _gather_honours(
        confirmed=plans, club_qid=qid, club_name=job.club_name,
        country_code=job.country_code,
    )
    if not result["league_wins"]:
        raise AutoResearchError("no_honours_found")
    with transaction.atomic():
        locked = ProductionJob.objects.select_for_update().get(
            pk=job.pk, owner_id=owner_id,
        )
        current = FactDossier.objects.filter(
            job=locked,
        ).order_by("-version").first()
        if current is None:
            raise AutoResearchError("stale_dossier")
        if _already_imported(current, qid):
            return current
        if current.version != expected_version or _club_qid(current) != qid:
            raise AutoResearchError("stale_dossier")
        updated_plans = _official_sources(current, owner_id)
        if any(
            (plans[role] is None) != (updated_plans[role] is None)
            or (
                plans[role] is not None and (
                    plans[role].source_url != updated_plans[role].source_url
                    or plans[role].confirmation_checked_at !=
                    updated_plans[role].confirmation_checked_at
                )
            ) for role in ("club", "league")
        ):
            raise AutoResearchError("stale_dossier")
        if FactDossier.objects.filter(
            job=locked,
            created_at__gte=timezone.now() - timedelta(minutes=1),
        ).count() >= 10:
            raise AutoResearchError("version_rate_limited")
        dossier = fork_dossier(job=locked, previous=current)
        league = SourceReference.objects.create(
            dossier=dossier,
            url=result["league_url"],
            source_kind=SourceReference.Kind.LEAGUE_OFFICIAL,
            title="[auto] Official league historical champions and cup winners",
            external_id=_HONOURS_MARKER + qid,
            retrieved_at=result["retrieved_at"],
            access_state=SourceReference.Access.ACCESSIBLE,
        )
        club = None
        if result["club_wins"] is not None and result["club_url"]:
            club = SourceReference.objects.create(
                dossier=dossier, url=result["club_url"],
                source_kind=SourceReference.Kind.CLUB_OFFICIAL,
                title="[auto] Official club national honours profile",
                external_id="auto-honours-club:" + qid,
                retrieved_at=result["retrieved_at"],
                access_state=SourceReference.Access.ACCESSIBLE,
            )

        wins = result["league_wins"]
        club_wins = result["club_wins"]
        entries = set(wins) | (set(club_wins) if club_wins is not None else set())
        if len(entries) > _MAX_WINNERS:
            raise AutoResearchError("too_many_honours")
        for season, category in sorted(entries):
            in_league = (season, category) in wins
            in_club = club_wins is not None and (season, category) in club_wins
            status = (
                "both" if in_league and in_club
                else "league_only" if in_league and club_wins is not None
                else "club_only" if in_club
                else "club_not_checked"
            )
            name = _TITLE_TYPES[category]
            if in_league:
                assertion = (
                    f"The official league records {locked.club_name} as "
                    f"{name} in {season}."
                )
            else:
                assertion = (
                    f"The official club profile lists {season} as a "
                    f"{name} season; this is not corroborated by the "
                    "league's title table."
                )
            fact = Fact.objects.create(
                dossier=dossier,
                predicate="club_honour_candidate",
                value={
                    "season": season, "category": category,
                    "corroboration": status,
                },
                assertion_text=assertion,
                verification_state=Fact.Verification.UNVERIFIED,
            )
            if in_league:
                Evidence.objects.create(
                    fact=fact, source=league, role=Evidence.Role.UNKNOWN,
                    locator=f"Season {season} · "
                    + ("Meister" if category == "league_champion" else "Cup-Sieger"),
                    summary=(
                        f"Official league winners table lists {locked.club_name} "
                        f"for {season} ({category}); automatically parsed, "
                        "not human reviewed."
                    ),
                )
            if in_club and club is not None:
                Evidence.objects.create(
                    fact=fact, source=club, role=Evidence.Role.UNKNOWN,
                    locator=f"National success · {season} · {category}",
                    summary=(
                        f"Club's published national success profile lists "
                        f"this season for {category}. Separate club-domain "
                        "source; automatically matched, not human reviewed."
                    ),
                )
        return dossier
