"""Run the dedicated queued-film worker (not in Django's web request path).

The --once mode is useful for CI and inspection. The single Docker worker
uses --loop; no network calls or paid APIs happen before a job is queued.
"""
import time

from django.core.management.base import BaseCommand

from app.production.film_worker import (
    recover_stale_film_jobs, run_film_worker_once,
)


class Command(BaseCommand):
    help = "Run durable film research jobs. Rendering is not yet implemented."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--once", action="store_true",
            help="Try to process one queued film job and exit.",
        )
        group.add_argument(
            "--loop", action="store_true",
            help="Run continually as the single Docker film-worker service.",
        )
        parser.add_argument(
            "--interval", type=int, default=10,
            help="Seconds between empty-queue checks (2 to 60).",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        if not 2 <= interval <= 60:
            from django.core.management.base import CommandError
            raise CommandError("--interval must be between 2 and 60.")
        if not options["loop"]:
            claimed = run_film_worker_once()
            self.stdout.write(
                f"Film research worker: {'processed job #' + str(claimed) if claimed else 'queue empty'}."
            )
            return
        self.stdout.write("Film production worker started; one process, persistent database queue.")
        while True:
            try:
                recovered = recover_stale_film_jobs()
                if recovered:
                    self.stdout.write(f"Recovered {recovered} stale film job(s).")
                claimed = run_film_worker_once()
                if claimed is None:
                    time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write("Film production worker shutting down.")
                return
