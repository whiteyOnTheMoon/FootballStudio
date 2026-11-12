"""Explicit single-use official research runner. NEVER invoked by an HTTP view.

Usage (after inspecting a *fresh*, owner-confirmed, 15-minute consent):
    python manage.py run_official_research_request \
        --job-id 1 --request-id 42 --owner-id 7 --execute

There is no queue, scheduler, periodic poller or automatic retry. This
command must be invoked explicitly and uses a Linux/Unix SIGALRM hard cap.
A live domain can block the request; no robots/CAPTCHA/403/429 bypass.
"""
from contextlib import contextmanager
import os
import signal
import threading

from django.core.management.base import BaseCommand, CommandError

from app.production.one_time_research_worker import (
    ResearchRunRejected, execute_one_time_research,
)
from app.production.safe_official_fetch import WebsiteFetchError


_HARD_TIMEOUT_SECONDS = 70


@contextmanager
def _hard_time_limit():
    # Explicit fail-closed requirement rather than claiming a hard deadline
    # on a platform unable to enforce one around blocking DNS or sockets.
    if (
        os.name != "posix"
        or threading.current_thread() is not threading.main_thread()
        or not hasattr(signal, "setitimer")
    ):
        raise CommandError("This command requires a POSIX main-thread deadline.")

    def timeout_handler(_signum, _frame):
        raise WebsiteFetchError("research_deadline")

    old_handler = signal.getsignal(signal.SIGALRM)
    old_timer = signal.getitimer(signal.ITIMER_REAL)
    if old_timer[0] > 0:
        raise CommandError("An existing alarm is already active.")
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, _HARD_TIMEOUT_SECONDS)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


class Command(BaseCommand):
    help = (
        "Consume exactly one still-valid source consent and run a bounded "
        "robots/SSRF-safe fetch; never schedule or retry automatically."
    )

    def add_arguments(self, parser):
        parser.add_argument("--job-id", type=int, required=True)
        parser.add_argument("--request-id", type=int, required=True)
        parser.add_argument("--owner-id", type=int, required=True)
        parser.add_argument(
            "--execute", action="store_true",
            help="Explicitly approve consuming this already-saved one-time consent.",
        )

    def handle(self, *args, **options):
        if not options["execute"]:
            raise CommandError(
                "Nothing ran. Re-run with --execute only after reviewing the "
                "job, owner, source and valid single-use consent."
            )
        try:
            with _hard_time_limit():
                outcome = execute_one_time_research(
                    owner_id=options["owner_id"], job_id=options["job_id"],
                    request_id=options["request_id"],
                )
        except ResearchRunRejected as exc:
            raise CommandError(f"Research not started: {exc}") from None
        if outcome["status"] != "succeeded":
            raise CommandError(
                "Single attempt stopped; no pages imported. "
                f"Safe error code: {outcome['code']}"
            )
        self.stdout.write(self.style.SUCCESS(
            f"Request #{outcome['request_id']} succeeded. "
            f"Unverified metadata stored in dossier v{outcome['dossier_version']}. "
            "No facts were verified."
        ))
