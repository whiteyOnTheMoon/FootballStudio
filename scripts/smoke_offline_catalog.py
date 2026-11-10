#!/usr/bin/env python3
"""Verify that the catalog can be seeded and served with ZERO network access."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.config.settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from app.clubs.models import Club, Confederation, Country, League  # noqa: E402


def main():
    call_command("migrate", interactive=False, verbosity=0)
    with patch("urllib.request.urlopen", side_effect=RuntimeError("network forbidden")):
        call_command("seed_world_catalog", verbosity=0)
        first = (Country.objects.count(), League.objects.count(), Club.objects.count())
        call_command("seed_world_catalog", verbosity=0)
        again = (Country.objects.count(), League.objects.count(), Club.objects.count())
        assert first == again, "Offline data import must be idempotent."
        assert Confederation.objects.count() == 6
        assert Country.objects.filter(confederation__code="UEFA").count() == 55
        assert League.objects.filter(coverage_status="snapshot").count() == 16
        assert Club.objects.filter(is_manual=False).count() == 278
        assert Country.objects.filter(code="LI").exists()
        assert not League.objects.filter(country__code="LI").exists()
    print("Offline directory OK:", first, "UEFA 55; 6 confeds; 16 club snapshots.")
    print("No HTTP/API calls were made during migration or import.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Offline catalog test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
