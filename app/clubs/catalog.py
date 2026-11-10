"""Offline catalog metadata. NO network fetching during normal user selection.

All confederations, member associations, leagues and available team names come
from PostgreSQL. Snapshot refreshes require an explicitly reviewed data update
and a seed_world_catalog invocation, never a timed user-request API call.
"""
from datetime import date

from django.utils import timezone


def season_start(today: date | None = None) -> int:
    today = today or timezone.localdate()
    return today.year if today.month >= 7 else today.year - 1


def season_label(year: int) -> str:
    return f"{year}-{(year + 1) % 100:02d}"
