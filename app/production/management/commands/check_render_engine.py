"""Operator-only, offline TTS/FFmpeg readiness and synthetic MP4 smoke check.

No real film data, no persistent files, no internet/paid provider use.
This command is not called by HTTP views or an ordinary film job.
"""
from django.core.management.base import BaseCommand, CommandError

from app.production.local_render import (
    RenderEngineError, inspect_render_stack, run_synthetic_render_smoke,
)


class Command(BaseCommand):
    help = (
        "Check whether the local TTS/FFmpeg pipeline is present; use "
        "--smoke to create and delete a neutral synthetic MP4."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--smoke", action="store_true",
            help="Actually encode and ffprobe a short original test clip.",
        )

    def handle(self, *args, **options):
        try:
            if options["smoke"]:
                result = run_synthetic_render_smoke()
                self.stdout.write(self.style.SUCCESS(
                    f"LOCAL RENDER SMOKE OK: {result['width']}x{result['height']}, "
                    f"{result['video_codec']}/{result['audio_codec']}, "
                    f"{result['duration_seconds']:.2f}s, "
                    f"{result['size_bytes']} bytes. "
                    "Temporary test files removed. "
                    "NO documentary or export produced."
                ))
            else:
                result = inspect_render_stack()
                self.stdout.write(self.style.SUCCESS(
                    "Local renderer prerequisites found: ffmpeg, ffprobe, "
                    "espeak-ng and original-graphics font. "
                    "Use --smoke for an actual encode test. "
                    "NO documentary completed."
                ))
        except RenderEngineError as exc:
            raise CommandError(
                f"Local renderer check failed: {exc}"
            ) from None
