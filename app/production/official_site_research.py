"""Opt-in, small read-only research pass for a confirmed official club/league.

Never invoked by the public web UI. A human must independently confirm the
club/league identity and the site's permissions before calling this service.
No facts are marked verified, no text articles are saved and no paid APIs run.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.robotparser import RobotFileParser
from urllib.parse import unquote, urlsplit
import re
import time

from .models import ProductionJob
from .official_site_links import discover_official_pages
from .safe_official_fetch import (
    WebsiteFetchError, _checked_url, _download_public_https, _USER_AGENT,
)


_MAX_SUBPAGES = 3
_MIN_DELAY_SECONDS = 2
_MAX_DELAY_SECONDS = 30


class _PageOutline(HTMLParser):
    """Only retain short titles/headings, never protected article body text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._active = None
        self._skip = 0
        self._parts = []
        self.title = ""
        self.headings = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self._skip += 1
        elif self._skip == 0 and tag in ("title", "h1", "h2"):
            self._active = tag
            self._parts = []

    def handle_data(self, data):
        if self._active and self._skip == 0:
            self._parts.append(data[:250])
            if len(self._parts) > 4:
                self._parts = self._parts[:4]

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template"):
            self._skip = max(0, self._skip - 1)
        if self._active == tag:
            value = " ".join(" ".join(self._parts).split())[:160]
            if tag == "title" and not self.title:
                self.title = value
            elif tag in ("h1", "h2") and value and len(self.headings) < 5:
                self.headings.append(value)
            self._active = None
            self._parts = []


class _RobotsGate:
    """Conservative overlay for Python's first-match robots parser.

    Python 3.12's RobotFileParser uses first matching rule, while RFC 9309
    specifies longest match and merging matching groups. We additionally
    honor ALL applicable explicit Disallow patterns, even where an Allow
    exception exists. This may skip otherwise permitted pages, but can never
    bypass an explicit Disallow because of ordering or duplicate groups.
    """

    def __init__(self, parser, text):
        self.parser = parser
        self.groups = []
        agents, rules = [], []
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                if agents and rules:
                    self.groups.append((agents, rules))
                    agents, rules = [], []
                continue
            name, colon, value = line.partition(":")
            if not colon:
                continue
            name, value = name.strip().lower(), value.strip()
            if name == "user-agent":
                if agents and rules:
                    self.groups.append((agents, rules))
                    agents, rules = [], []
                if value:
                    agents.append(value.lower())
            elif name in ("allow", "disallow") and agents:
                rules.append((name, value))
        if agents:
            self.groups.append((agents, rules))

    def can_fetch(self, agent, url):
        if not self.parser.can_fetch(agent, url):
            return False
        product = agent.split("/", 1)[0].lower()
        matching = [g for g in self.groups
                    if any(a != "*" and a in product for a in g[0])]
        if not matching:
            matching = [g for g in self.groups if "*" in g[0]]
        path = urlsplit(url).path or "/"
        # Use both encoded and decoded variants to avoid underblocking
        # when an origin decodes URI path segments before routing.
        for _, rules in matching:
            for directive, pattern in rules:
                if directive != "disallow" or not pattern:
                    continue
                end_anchor = pattern.endswith("$")
                escaped = re.escape(pattern.rstrip("$")).replace(r"\*", ".*")
                regex = "^" + escaped + ("$" if end_anchor else "")
                if re.match(regex, path) or re.match(regex, unquote(path)):
                    return False
        return True


def _robots_policy(homepage_url):
    canonical, host = _checked_url(homepage_url)
    robots_url = f"https://{host}/robots.txt"
    # A missing/redirecting/blocked robots.txt fails closed (more restrictive
    # than the RFC's permission to treat certain 4xx responses as available).
    contents = _download_public_https(robots_url, kind="robots")
    if not contents.strip() or not any(
        line.lstrip().lower().startswith("user-agent:")
        for line in contents.splitlines()
    ):
        raise WebsiteFetchError("robots_unusable")
    parser = RobotFileParser()
    try:
        parser.parse(contents.splitlines())
        delay = parser.crawl_delay(_USER_AGENT.split("/", 1)[0]) or 0
        request_rate = parser.request_rate(_USER_AGENT.split("/", 1)[0])
    except (ValueError, TypeError, AttributeError):
        raise WebsiteFetchError("robots_unusable") from None
    if request_rate:
        if request_rate.requests <= 0:
            raise WebsiteFetchError("robots_unusable")
        delay = max(delay, request_rate.seconds / request_rate.requests)
    delay = max(_MIN_DELAY_SECONDS, delay)
    if delay > _MAX_DELAY_SECONDS:
        raise WebsiteFetchError("crawl_delay_too_long")
    return robots_url, _RobotsGate(parser, contents), delay


def _outline(url, html):
    metadata = _PageOutline()
    metadata.feed(html)
    return {
        "url": url,
        "title": metadata.title,
        "headings": metadata.headings,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "verification_state": "unverified",
    }


def research_official_website(*, owner, job_id, homepage_url, context,
                              identity_confirmed=False, terms_confirmed=False):
    """Read homepage + <=3 same-host pages after strict, explicit approvals.

    This returns unverified page metadata. Nothing is stored in the DB; the
    future fact dossier workflow must review each sourced assertion itself.
    """
    if identity_confirmed is not True or terms_confirmed is not True:
        raise ValueError("Explicit identity and site-terms confirmation required.")
    if context not in ("club", "league"):
        raise ValueError("Research context must be 'club' or 'league'.")
    homepage_url, original_host = _checked_url(homepage_url)

    # Ensure the caller owns the job BEFORE robots or any site request.
    job = ProductionJob.objects.select_related("club__league").get(
        pk=job_id, owner=owner,
    )

    robots_url, robots, delay = _robots_policy(homepage_url)
    if not robots.can_fetch(_USER_AGENT, homepage_url):
        raise WebsiteFetchError("robots_disallowed")

    # Always observe politeness delay between robots and the homepage too.
    time.sleep(delay)
    html = _download_public_https(homepage_url, kind="html")
    pages = [_outline(homepage_url, html)]

    candidates = discover_official_pages(homepage_url, html, context=context,
                                         limit=_MAX_SUBPAGES)
    for candidate in candidates:
        candidate_url, candidate_host = _checked_url(candidate["url"])
        if candidate_host != original_host:
            raise WebsiteFetchError("unsafe_url")
        if not robots.can_fetch(_USER_AGENT, candidate_url):
            # Do not attempt disallowed pages and do not substitute other paths
            # or try to bypass the website's stated preference.
            continue
        time.sleep(delay)
        body = _download_public_https(candidate_url, kind="html")
        page = _outline(candidate_url, body)
        page["category"] = candidate["category"]
        pages.append(page)

    return {
        "job_id": job.pk,
        "club_id": job.club_id,
        "league_id": job.club.league_id,
        "context": context,
        "site_url": homepage_url,
        "robots_url": robots_url,
        "pages": pages,
        "source_status": "unverified",
        "stored": False,
    }
