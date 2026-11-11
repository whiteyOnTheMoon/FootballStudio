"""Bounded, offline discovery of research pages on a confirmed club website.

This module NEVER performs network access. Only the future HTTP adapter may
fetch candidates, after robots.txt, DNS, redirects and rate limits are checked.
"""
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import urljoin, urlsplit, urlunsplit


_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_BLOCKED = {
    "account", "accounts", "admin", "bet", "betting", "basket", "cart",
    "checkout", "cookie", "cookies", "donate", "download", "fanshop",
    "login", "logout", "register", "shop", "signin", "signup", "sponsor",
    "store", "ticket", "tickets",
}
_CATEGORIES = (
    ("history", 100, {"history", "historie", "geschichte", "historia", "histoire", "storia", "chronik", "historique"}),
    ("honours", 90, {"honours", "honors", "titles", "trophies", "erfolge", "palmares", "trophees", "titel", "trofei", "titulos"}),
    ("stadium", 80, {"stadium", "stadion", "stade", "estadio", "stadio", "arena"}),
    ("about", 70, {"about", "verein", "club", "clube", "societa", "societe", "institution", "profil", "aboutus"}),
    ("team", 60, {"team", "teams", "squad", "mannschaft", "kader", "equipo", "equipe", "rosa"}),
)
_MAX_HTML_CHARS = 300_000


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.active = None

    def handle_starttag(self, tag, attrs):
        if tag != "a" or self.active is not None:
            return
        properties = dict(attrs)
        href = properties.get("href")
        if not isinstance(href, str):
            return
        if "nofollow" in (properties.get("rel") or "").lower().split():
            return
        if "download" in properties:
            return
        self.active = [href, properties.get("title") or "", []]

    def handle_data(self, data):
        if self.active:
            self.active[2].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.active:
            href, title, parts = self.active
            self.links.append((href, title + " " + " ".join(parts)))
            self.active = None


def _tokens(value):
    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_only = "".join(c for c in normalized if not unicodedata.combining(c))
    return set(re.findall(r"[a-z0-9]+", ascii_only))


def _homepage(homepage_url):
    if not isinstance(homepage_url, str):
        raise ValueError("An explicit HTTPS homepage is required.")
    try:
        url = urlsplit(homepage_url)
        hostname = url.hostname
        port = url.port
    except ValueError:
        raise ValueError("Invalid homepage URL.") from None
    if (
        url.scheme != "https" or not hostname or port is not None
        or url.username is not None or url.password is not None
        or url.query or url.fragment
        or len(hostname) > 253 or not hostname.isascii()
        or "." not in hostname or hostname.endswith((".local", ".localhost", ".internal"))
        or not all(_HOST_LABEL.fullmatch(label) for label in hostname.split("."))
        or hostname.split(".")[-1].isdigit()
    ):
        raise ValueError("An explicit public HTTPS club homepage is required.")
    return urlunsplit(("https", hostname.lower(), url.path or "/", "", "")), hostname.lower()


def discover_official_pages(homepage_url, homepage_html, *, limit=8):
    """Rank same-host internal links from HTML already obtained elsewhere.

    Does NOT prove the hostname belongs to the club, check robots.txt or
    fetch any page. Returned candidates are proposals for subsequent review.
    """
    base_url, hostname = _homepage(homepage_url)
    if not isinstance(homepage_html, str) or len(homepage_html) > _MAX_HTML_CHARS:
        raise ValueError("Expected a bounded HTML string.")
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("limit must be an integer between 1 and 10")

    parser = _Links()
    parser.feed(homepage_html)
    candidates = {}
    for href, label in parser.links:
        if not href or href.startswith("#"):
            continue
        try:
            combined = urljoin(base_url, href.strip())
            target = urlsplit(combined)
            if (
                target.scheme != "https" or target.hostname != hostname
                or target.port is not None
                or target.username is not None or target.password is not None
                or target.query
            ):
                continue
        except ValueError:
            continue
        path = target.path or "/"
        if path == urlsplit(base_url).path:
            continue
        if path.lower().endswith((".pdf", ".jpg", ".jpeg", ".png", ".svg",
                                  ".zip", ".mp4", ".webp", ".xml", ".json")):
            continue
        tokens = _tokens(path + " " + label)
        if tokens & _BLOCKED:
            continue
        category = next(
            ((name, score) for name, score, keywords in _CATEGORIES
             if tokens & keywords), None,
        )
        if category is None:
            continue
        # Ignore fragments and URL query strings: no tracking, tokens or session IDs.
        canonical = urlunsplit(("https", hostname, path, "", ""))
        name, score = category
        item = {
            "url": canonical,
            "category": name,
            "label": " ".join(label.split())[:160],
            "priority": score,
        }
        if canonical not in candidates or score > candidates[canonical]["priority"]:
            candidates[canonical] = item
    return sorted(candidates.values(), key=lambda entry: (
        -entry["priority"], entry["url"],
    ))[:limit]
