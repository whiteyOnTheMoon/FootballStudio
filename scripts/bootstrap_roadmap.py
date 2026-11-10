#!/usr/bin/env python3
"""Idempotent GitHub repository metadata bootstrap for FootballStudio.

Uses only GitHub Actions' built-in GITHUB_TOKEN with repository Issues write
permission. Creates milestones, labels and applies them to existing issues.
GitHub Projects v2 is intentionally NOT created: it needs separate permissions.
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


REPO = os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
ALLOWED_REPO = "whiteyOnTheMoon/FootballStudio"

MILESTONES = {
    "M0": "Anforderungen, Architektur und Rahmenbedingungen",
    "M1": "Docker-Web-App, Datenbank, Login und dynamische Vereinswahl",
    "M2": "Erste komplette englische, quellengestützte Dokumentation",
    "M3": "Faktenqualität, Medienrechte, Zuverlässigkeit und Kosten",
    "M4": "Video-Templates, Karten, Infografiken und Metadaten",
    "M5": "Sprachvarianten de, fr, it, es, pt",
    "M6": "Automatisierung, Warteschlange und optionale Veröffentlichung",
}
LABELS = {
    **{f"priority:P{i}": ("b60205" if i == 0 else "d4c5f9") for i in range(4)},
    **{f"type:{name}": "bfdadc" for name in
       ("docs", "feature", "research", "infra", "test", "security", "bug")},
    **{f"area:{name}": "c2e0c6" for name in
       ("web", "backend", "research", "media", "audio", "render", "ops")},
    **{f"status:{name}": "e4e8ec" for name in
       ("Backlog", "Ready", "In Progress", "Review/Test", "Done")},
}
LABEL_DESCRIPTIONS = {
    "priority:P0": "Blocker: notwendig vor nachgelagerten MVP-Arbeiten",
    "priority:P1": "MVP-Priorität",
    "priority:P2": "Nach dem MVP",
    "priority:P3": "Optionaler Ausbau",
}


def api(method: str, route: str, body: dict | None = None):
    encoded = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(
        "https://api.github.com" + route,
        data=encoded,
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "FootballStudio-roadmap-bootstrap",
        },
        method=method,
    )
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else None
    except HTTPError as exc:
        # The authentication header is never included in the error message.
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        print(f"GitHub {method} {route}: HTTP {exc.code}: {detail}", file=sys.stderr)
        raise


def all_pages(route: str):
    items = []
    for page in range(1, 100):
        sep = "&" if "?" in route else "?"
        batch = api("GET", f"{route}{sep}per_page=100&page={page}")
        if not isinstance(batch, list):
            raise RuntimeError("Expected paginated GitHub list response")
        items.extend(batch)
        if len(batch) < 100:
            return items
    raise RuntimeError("Unexpectedly many GitHub pages; refusing incomplete metadata")


def get_field(body: str, field: str) -> str | None:
    # Existing roadmap issues store metadata in markdown, e.g. **Priorität:** P0
    match = re.search(r"\*\*" + re.escape(field) + r":\*\*\s*([A-Za-z0-9_-]+)", body)
    return match.group(1) if match else None


def ensure_milestones(prefix: str):
    found = {item["title"]: item["number"] for item in
             all_pages(prefix + "/milestones?state=all")}
    for name, description in MILESTONES.items():
        if name not in found:
            entry = api("POST", prefix + "/milestones",
                        {"title": name, "description": description, "state": "open"})
            found[name] = entry["number"]
            print("Created milestone:", name)
    return found


def ensure_labels(prefix: str):
    found = {entry["name"] for entry in all_pages(prefix + "/labels")}
    for name, color in LABELS.items():
        if name not in found:
            api("POST", prefix + "/labels",
                {"name": name, "color": color,
                 "description": LABEL_DESCRIPTIONS.get(name, "FootballStudio roadmap tracking")})
            print("Created label:", name)


def organize_issues(prefix: str, milestone_numbers: dict):
    assigned = 0
    labeled = 0
    for issue in all_pages(prefix + "/issues?state=all"):
        if "pull_request" in issue:
            continue
        m = re.match(r"^(M[0-6])\s*/", issue["title"])
        if not m:
            continue
        number = issue["number"]
        milestone = milestone_numbers[m.group(1)]
        existing_milestone = (issue.get("milestone") or {}).get("number")
        if existing_milestone != milestone:
            api("PATCH", f"{prefix}/issues/{number}", {"milestone": milestone})
            assigned += 1

        existing_labels = {x["name"] for x in issue.get("labels", [])}
        wanted = set()
        body = issue.get("body") or ""
        for kind, allowed in (
            ("Priorität", ("P0", "P1", "P2", "P3")),
            ("Typ", ("docs", "feature", "research", "infra", "test", "security", "bug")),
            ("Bereich", ("web", "backend", "research", "media", "audio", "render", "ops")),
        ):
            found = get_field(body, kind)
            if found and found in allowed:
                category = {"Priorität": "priority", "Typ": "type", "Bereich": "area"}[kind]
                wanted.add(f"{category}:{found}")

        if issue["state"] == "closed":
            wanted.add("status:Done")
            # Prevent an already closed issue from retaining a stale status.
            for label in existing_labels:
                if label.startswith("status:") and label != "status:Done":
                    api("DELETE", f"{prefix}/issues/{number}/labels/{quote(label, safe='')}")
                    existing_labels.discard(label)
        elif not any(label.startswith("status:") for label in existing_labels):
            wanted.add("status:Backlog")

        missing = sorted(wanted - existing_labels)
        if missing:
            api("POST", f"{prefix}/issues/{number}/labels", {"labels": missing})
            labeled += 1
    print(f"Finished: milestones updated for {assigned} issues; labels added to {labeled} issues.")


def main():
    if REPO != ALLOWED_REPO:
        raise SystemExit(f"Refusing to update unexpected repository: {REPO!r}")
    if not TOKEN:
        raise SystemExit("Missing GITHUB_TOKEN")
    prefix = "/repos/" + REPO
    milestone_numbers = ensure_milestones(prefix)
    ensure_labels(prefix)
    organize_issues(prefix, milestone_numbers)
    print("GitHub Projects v2 board remains a separate issue: repository token cannot create it.")


if __name__ == "__main__":
    main()
