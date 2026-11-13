"""FS-014a: guarded official club legend-list matching (free, no LLM).

The association between a Wikidata person and an official legend entry is
an automatically *proposed* match, not a human FactReview or script approval.

Only a prior owner-confirmed official club domain may be fetched. The
existing DNS-pinned TLS/robots implementation is reused without bypass.
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
    Evidence, Fact, FactDossier, ProductionJob, SourceConfirmation,
    SourceReference,
)
from .official_site_research import _robots_policy
from .safe_official_fetch import (
    WebsiteFetchError, _checked_url, _download_public_https, _USER_AGENT,
)
from .wikimedia_auto import AutoResearchError

# A path hint is a discovery aide, NOT a name list, truth assertion or
# exception to source consent / robots / TLS. The generic path finder works
# for sites whose homepage exposes a legend page.
_KNOWN_CLUB_PATHS = {
    ("Q124007617", "sksturm.at"): "/c/legendenklub",
}
_MAX_PEOPLE = 30
_MAX_TRAINERS = 12
_MAX_HTML_LENGTH = 300_000
_MAX_LOOKUP_SECONDS = 40
_QID = re.compile(r"Q[1-9][0-9]{0,11}\Z")
_NAME = re.compile(r"[^<>\r\n\t]{2,120}\Z")
_LINK_TOKENS = (
    "legenden", "legende", "legend", "legends", "hall-of-fame",
    "hall_of_fame", "ehren", "ikonen",
)


def _clean_person(value):
    if not isinstance(value, str):
        return ""
    value = " ".join(value.strip().split())
    if not _NAME.fullmatch(value) or not value.isprintable():
        return ""
    # No fuzzy matching: diacritics and word order remain significant.
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return normalized


class _LegendPage(HTMLParser):
    """Small text-only club list parser, with strict heading boundaries.

    Only comma-/semicolon-delimited name lists within the explicit headings
    'player legends'/'trainer legends' are accepted. News paragraphs,
    navigation, captions, quotes or headings elsewhere are ignored.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.heading_tag = ""
        self.heading_parts = []
        self.active = None
        self.parts = []
        self.people = {"player": [], "trainer": []}
        self.seen_section = {"player": False, "trainer": False}

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template", "svg"):
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in ("h1", "h2", "h3", "h4"):
            self._finish_text()
            self.heading_tag = tag
            self.heading_parts = []
        elif tag in ("p", "li") and self.active:
            self._finish_text()
            self.parts = []

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.heading_tag:
            self.heading_parts.append(data[:300])
        elif self.active:
            self.parts.append(data[:1000])

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template", "svg"):
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag == self.heading_tag:
            heading = " ".join(" ".join(self.heading_parts).split()).casefold()
            self.heading_tag = ""
            self.heading_parts = []
            if any(x in heading for x in ("trainerlegenden", "coaching legends", "trainer legends")):
                self.active = "trainer"
                self.seen_section["trainer"] = True
            elif any(x in heading for x in ("spielerlegenden", "player legends", "players legends")):
                self.active = "player"
                self.seen_section["player"] = True
            elif tag in ("h1", "h2"):
                self.active = None
            return
        if tag in ("p", "li") and self.active:
            self._finish_text()

    def _finish_text(self):
        if not self.active or not self.parts:
            self.parts = []
            return
        value = " ".join(" ".join(self.parts).split())
        self.parts = []
        # Deliberately require a visible list, not a paragraph that happens
        # to mention a person's name in a story.
        if not 4 <= len(value) <= 3500 or "," not in value:
            return
        for fragment in re.split(r"[,;]", value):
            name = " ".join(fragment.split())
            if (
                _clean_person(name)
                and len(self.people[self.active]) < (
                    _MAX_TRAINERS if self.active == "trainer"
                    else 160
                )
            ):
                self.people[self.active].append(name)


def extract_official_legend_list(html):
    """Return names by role, or fail closed on absent/ambiguous sections."""
    if not isinstance(html, str) or not 1 <= len(html) <= _MAX_HTML_LENGTH:
        raise AutoResearchError("invalid_legend_page")
    parser = _LegendPage()
    try:
        parser.feed(html)
        parser.close()
    except (ValueError, TypeError):
        raise AutoResearchError("invalid_legend_page") from None
    if not parser.seen_section["player"] and not parser.seen_section["trainer"]:
        raise AutoResearchError("no_legend_sections")
    result = {}
    for role, raw in parser.people.items():
        distinct = {}
        for name in raw:
            key = _clean_person(name)
            if key and key not in distinct:
                distinct[key] = name
        if role == "trainer" and len(distinct) > _MAX_TRAINERS:
            raise AutoResearchError("ambiguous_legend_list")
        result[role] = distinct
    if not any(result.values()):
        raise AutoResearchError("no_legend_names")
    return result


class _LegendLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.options = []
        self.active_href = None
        self.active_words = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        data = dict(attrs)
        if not isinstance(data.get("href"), str):
            return
        if "nofollow" in (data.get("rel") or "").lower().split():
            return
        self.active_href = data["href"]
        self.active_words = [data.get("title", "")]

    def handle_data(self, data):
        if self.active_href is not None:
            self.active_words.append(data[:250])

    def handle_endtag(self, tag):
        if tag == "a" and self.active_href is not None:
            self.options.append((self.active_href, " ".join(self.active_words)))
            self.active_href = None
            self.active_words = []


def _discover_link(homepage, html):
    """Find <=1 plausible on-domain legend list; never guess other hosts."""
    if not isinstance(html, str) or len(html) > _MAX_HTML_LENGTH:
        raise AutoResearchError("invalid_homepage")
    parser = _LegendLinks()
    parser.feed(html)
    base, host = _checked_url(homepage)
    links = set()
    for href, label in parser.options[:300]:
        if not any(t in (href + " " + label).casefold() for t in _LINK_TOKENS):
            continue
        try:
            url = urljoin(base, href)
            normalized, found_host = _checked_url(url)
        except (ValueError, WebsiteFetchError):
            continue
        if found_host != host or normalized == base:
            continue
        if any(normalized.endswith(x) for x in (".pdf", ".xml", ".jpg", ".json")):
            continue
        links.add(normalized)
    if len(links) != 1:
        raise AutoResearchError("no_unique_legends_link")
    return next(iter(links))


def _approved_source(job, latest, owner_id):
    """Check prior user-affirmed site identity and TOS, not just URL strings."""
    sources = list(SourceReference.objects.filter(
        dossier=latest, source_kind=SourceReference.Kind.CLUB_OFFICIAL,
        access_state=SourceReference.Access.ACCESSIBLE,
    ).select_related("manual_confirmation").order_by("pk"))
    eligible = []
    for source in sources:
        try:
            confirmation = source.manual_confirmation
        except SourceConfirmation.DoesNotExist:
            continue
        if (
            confirmation.reviewer_id != owner_id
            or confirmation.identity_confirmed is not True
            or confirmation.terms_confirmed is not True
            or confirmation.access_confirmed is not True
            or confirmation.checked_at is None
            or confirmation.checked_at > timezone.now() + timedelta(minutes=5)
        ):
            continue
        try:
            canonical, host = _checked_url(source.url)
        except WebsiteFetchError:
            continue
        if (
            canonical != source.url
            or host != confirmation.confirmed_domain
        ):
            continue
        eligible.append(source)
    if len(eligible) != 1:
        raise AutoResearchError("no_confirmed_club_source")
    return eligible[0]


def _auto_club_qid(dossier):
    sources = list(dossier.sources.filter(
        source_kind=SourceReference.Kind.WIKIDATA,
        title__startswith="[auto] ",
        external_id__regex=r"^Q[1-9][0-9]{0,11}$",
    ).order_by("pk")[:2])
    if len(sources) != 1:
        raise AutoResearchError("no_auto_research")
    qid = sources[0].external_id
    if (
        not _QID.fullmatch(qid) or
        sources[0].url !=
        f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    ):
        raise AutoResearchError("no_auto_research")
    return qid


def _already_compared(dossier, qid):
    return dossier.sources.filter(
        external_id="auto-official-legends:" + qid,
        source_kind=SourceReference.Kind.CLUB_OFFICIAL,
    ).exists()


def _read_official_legends(homepage, club_qid):
    """Guarded: robots, one homepage if needed, one official list (no crawling)."""
    started = time.monotonic()
    base, host = _checked_url(homepage)
    _robots_url, gate, delay = _robots_policy(base)
    path_hint = _KNOWN_CLUB_PATHS.get((club_qid, host))
    if path_hint is None:
        if not gate.can_fetch(_USER_AGENT, base):
            raise WebsiteFetchError("robots_disallowed")
        if time.monotonic() + delay + 5 >= started + _MAX_LOOKUP_SECONDS:
            raise WebsiteFetchError("research_deadline")
        time.sleep(delay)
        home_html = _download_public_https(base, kind="html")
        page_url = _discover_link(base, home_html)
    else:
        page_url = f"https://{host}{path_hint}"
    safe_page, same_host = _checked_url(page_url)
    if same_host != host:
        raise WebsiteFetchError("unsafe_url")
    if not gate.can_fetch(_USER_AGENT, safe_page):
        raise WebsiteFetchError("robots_disallowed")
    if time.monotonic() + delay + 5 >= started + _MAX_LOOKUP_SECONDS:
        raise WebsiteFetchError("research_deadline")
    time.sleep(delay)
    body = _download_public_https(safe_page, kind="html")
    extracted = extract_official_legend_list(body)
    return safe_page, extracted


def crosscheck_official_club_legends(*, owner, job_id, expected_version):
    """Cross-match P54 candidates plus discover club-named trainer legends.

    No automatic verified status, human reviewer impersonation, or script
    release. "Official list" means a website was actually fetched under
    source-specific consent + robots, NOT merely URL existence.
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
    latest = FactDossier.objects.filter(job=job).order_by("-version").first()
    if latest is None:
        raise AutoResearchError("no_auto_research")
    qid = _auto_club_qid(latest)
    if _already_compared(latest, qid):
        return latest
    if latest.version != expected_version:
        raise AutoResearchError("stale_dossier")
    source = _approved_source(job, latest, owner_id)
    people = list(latest.facts.filter(
        predicate="club_player_candidate",
    ).order_by("pk")[:12])
    if not people:
        raise AutoResearchError("no_player_candidates")
    candidates = {}
    for fact in people:
        if (
            fact.verification_state != Fact.Verification.UNVERIFIED
            or not isinstance(fact.value, dict)
        ):
            continue
        name = fact.value.get("name")
        name_key = _clean_person(name)
        if name_key and name_key not in candidates:
            candidates[name_key] = (name, fact.value.get("person_qid"))
    if not candidates:
        raise AutoResearchError("no_player_candidates")
    try:
        page_url, lists = _read_official_legends(source.url, qid)
    except WebsiteFetchError as exc:
        raise AutoResearchError("official_site_" + exc.code) from None

    found_players = [
        (name, person_qid) for key, (name, person_qid) in candidates.items()
        if key in lists["player"]
    ][:_MAX_PEOPLE]
    trainers = list(lists["trainer"].values())[:_MAX_TRAINERS]
    if not found_players and not trainers:
        raise AutoResearchError("no_legend_matches")

    with transaction.atomic():
        locked = ProductionJob.objects.select_for_update().get(
            pk=job.pk, owner_id=owner_id,
        )
        current = FactDossier.objects.filter(
            job=locked,
        ).order_by("-version").first()
        if current is None:
            raise AutoResearchError("stale_dossier")
        if _already_compared(current, qid):
            return current
        if current.version != expected_version:
            raise AutoResearchError("stale_dossier")
        _auto_club_qid(current)
        current_source = _approved_source(locked, current, owner_id)
        if (
            source.url != current_source.url
            or source.retrieved_at != current_source.retrieved_at
        ):
            raise AutoResearchError("stale_dossier")
        if FactDossier.objects.filter(
            job=locked,
            created_at__gte=timezone.now() - timedelta(minutes=1),
        ).count() >= 10:
            raise AutoResearchError("version_rate_limited")
        dossier = fork_dossier(job=locked, previous=current)
        fetched = timezone.now()
        official = SourceReference.objects.create(
            dossier=dossier, source_kind=SourceReference.Kind.CLUB_OFFICIAL,
            url=page_url, title="[auto] Official club legend roster",
            external_id="auto-official-legends:" + qid,
            retrieved_at=fetched,
            access_state=SourceReference.Access.ACCESSIBLE,
        )
        for name, person_qid in found_players:
            fact = Fact.objects.create(
                dossier=dossier, predicate="official_player_legend_candidate",
                value={
                    "name": name,
                    "person_qid": person_qid,
                    "club_qid": qid,
                    "match_basis": "exact_name_on_confirmed_official_club_list",
                },
                assertion_text=(
                    f"{name} is named in the club's published player-legends list."
                ),
                verification_state=Fact.Verification.UNVERIFIED,
            )
            Evidence.objects.create(
                fact=fact, source=official, role=Evidence.Role.UNKNOWN,
                locator="Official club legend roster · player section",
                summary=(
                    f"Exact visible roster-name match: {name}. "
                    "Automated comparison, not a human review."
                ),
            )
        for name in trainers:
            fact = Fact.objects.create(
                dossier=dossier, predicate="official_coach_legend_candidate",
                value={
                    "name": name, "club_qid": qid,
                    "match_basis": "name_on_confirmed_official_club_list",
                },
                assertion_text=(
                    f"{name} is named in the club's published coaching-legends list."
                ),
                verification_state=Fact.Verification.UNVERIFIED,
            )
            Evidence.objects.create(
                fact=fact, source=official, role=Evidence.Role.UNKNOWN,
                locator="Official club legend roster · coaching section",
                summary=(
                    f"Visible roster entry: {name}. "
                    "Automated extraction, not a human review."
                ),
            )
        return dossier
