"""FS-020: synthetic render is bounded, isolated and not a documentary."""
from io import StringIO
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from . import local_render
from .local_render import RenderEngineError, run_synthetic_render_smoke

_BIN = {
    "ffmpeg": "/bin/ffmpeg", "ffprobe": "/bin/ffprobe",
    "espeak-ng": "/bin/espeak-ng",
}


class LocalRenderTests(SimpleTestCase):
    def test_constant_original_artwork_contains_no_club_claims(self):
        filters = local_render._video_filter()
        self.assertEqual(filters.count("drawtext="), 3)
        self.assertIn("FootballStudio", filters)
        self.assertIn("Synthetic media only", filters)
        self.assertNotIn("Sturm Graz", filters)
        self.assertNotIn("Wikidata", filters)

    @patch("app.production.local_render._FONT")
    @patch("app.production.local_render.shutil.which")
    def test_absent_voice_binary_or_font_blocks_renderer(self, which, font):
        which.side_effect = lambda name: None if name == "espeak-ng" else "/bin/" + name
        with self.assertRaisesMessage(RenderEngineError, "missing_required_binary:espeak-ng"):
            local_render.inspect_render_stack()
        which.side_effect = lambda name: "/bin/" + name
        font.is_file.return_value = False
        with self.assertRaisesMessage(RenderEngineError, "missing_original_graphics_font"):
            local_render.inspect_render_stack()

    def simulate_tools(self, *, video_codec="h264", duration="3.17"):
        results = []
        def fake(args, *, timeout, input_data=None):
            self.assertLessEqual(timeout, 45)
            if args[0].endswith("espeak-ng"):
                self.assertIsInstance(input_data, bytes)
                self.assertIn(b"pipeline test", input_data)
                self.assertNotIn(b"Sturm", input_data)
                return b"RIFF" + b"\x00"*4 + b"WAVE" + b"\x00"*600
            if args[0].endswith("ffmpeg"):
                path = Path(args[-1])
                path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00"*3000)
                results.append(path)
                return b""
            return json.dumps({
                "streams": [
                    {"codec_type": "video", "codec_name": video_codec,
                     "width": 960, "height": 540},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"duration": duration},
            }).encode("utf-8")
        return fake, results

    @patch("app.production.local_render._tools", return_value=_BIN)
    @patch("app.production.local_render._execute")
    def test_mock_mp4_is_validated_and_deleted(self, execute, _tools):
        execute.side_effect, saved = self.simulate_tools()
        result = run_synthetic_render_smoke()
        self.assertTrue(result["passed"])
        self.assertEqual(result["video_codec"], "h264")
        self.assertEqual(result["audio_codec"], "aac")
        self.assertEqual(result["duration_seconds"], 3.17)
        self.assertEqual(result["paid_api_calls"], 0)
        self.assertEqual(result["network_calls"], 0)
        self.assertEqual(result["retained_files"], 0)
        self.assertFalse(result["documentary_completed"])
        self.assertEqual(len(saved), 1)
        self.assertFalse(saved[0].exists())
        self.assertEqual(execute.call_count, 3)

    @patch("app.production.local_render._tools", return_value=_BIN)
    @patch("app.production.local_render._execute")
    def test_wrong_codec_fails_and_leaves_no_artifact(self, execute, _tools):
        execute.side_effect, saved = self.simulate_tools(video_codec="vp9")
        with self.assertRaisesMessage(RenderEngineError, "unexpected_media_streams"):
            run_synthetic_render_smoke()
        self.assertEqual(len(saved), 1)
        self.assertFalse(saved[0].exists())

    @patch("app.production.local_render._tools", return_value=_BIN)
    @patch("app.production.local_render._execute")
    def test_invalid_probe_duration_fails(self, execute, _tools):
        execute.side_effect, _ = self.simulate_tools(duration="nan")
        with self.assertRaisesMessage(RenderEngineError, "unexpected_media_streams"):
            run_synthetic_render_smoke()

    @patch("app.production.local_render.subprocess.run")
    def test_subprocess_errors_are_sanitized_and_timeout_bounded(self, run):
        run.side_effect = subprocess.TimeoutExpired(["ffmpeg"], 1)
        with self.assertRaisesMessage(RenderEngineError, "tool_timeout"):
            local_render._execute(["ffmpeg", "--version"], timeout=1)
        run.side_effect = None
        run.return_value = subprocess.CompletedProcess(
            ["ffmpeg"], 1, stdout=b"", stderr=b"PRIVATE SECRET",
        )
        with self.assertRaisesMessage(RenderEngineError, "tool_execution_failed") as error:
            local_render._execute(["ffmpeg", "--version"], timeout=1)
        self.assertNotIn("PRIVATE SECRET", str(error.exception))

    @patch("app.production.management.commands.check_render_engine.run_synthetic_render_smoke")
    def test_operator_command_reports_synthetic_only(self, smoke):
        smoke.return_value = {
            "width": 960, "height": 540, "video_codec": "h264",
            "audio_codec": "aac", "duration_seconds": 3.1,
            "size_bytes": 4242,
        }
        stream = StringIO()
        call_command("check_render_engine", "--smoke", stdout=stream)
        self.assertIn("LOCAL RENDER SMOKE OK", stream.getvalue())
        self.assertIn("NO documentary", stream.getvalue())
        smoke.assert_called_once()

    @patch("app.production.management.commands.check_render_engine.inspect_render_stack")
    def test_operator_command_missing_tool_is_error(self, inspect):
        inspect.side_effect = RenderEngineError("missing_required_binary:ffmpeg")
        with self.assertRaisesRegex(CommandError, "missing_required_binary:ffmpeg"):
            call_command("check_render_engine")
