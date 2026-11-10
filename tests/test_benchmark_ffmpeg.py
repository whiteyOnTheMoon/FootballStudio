"""Offline tests for the FootballStudio synthetic FFmpeg benchmark.

The integration smoke test runs separately in GitHub Actions on an ephemeral
runner; these tests do not perform a full video render.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_ffmpeg.py"
SPEC = importlib.util.spec_from_file_location("benchmark_ffmpeg", SCRIPT)
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class FFmpegSizingTest(unittest.TestCase):
    def test_raw_video_frame_count_and_bitrate_estimate(self):
        # 10 minutes at 6 Mbps H.264 + 128 Kbps AAC, excluding all intermediates.
        self.assertEqual(benchmark.estimate_encoded_bytes(600, 6.0), 459_600_000)
        # 10 minutes at 2.5 Mbps video.
        self.assertEqual(benchmark.estimate_encoded_bytes(600, 2.5), 197_100_000)
        with self.assertRaises(ValueError):
            benchmark.estimate_encoded_bytes(0, 6.0)

    def test_profiles_are_fixed_and_video_has_explicit_codec(self):
        self.assertEqual(benchmark.RESOLUTIONS["720p"], (1280, 720))
        self.assertEqual(benchmark.RESOLUTIONS["1080p"], (1920, 1080))
        cmd = benchmark.command_for(1280, 720, 3, 2, Path("/tmp/studio-test.mp4"))
        self.assertIn("testsrc2=size=1280x720:rate=24", cmd)
        self.assertIn("libx264", cmd)
        self.assertIn("aac", cmd)
        self.assertNotIn("-i /private/real-media.mp4", " ".join(cmd))

    def test_rejects_unbounded_resource_consumption(self):
        with tempfile.TemporaryDirectory() as tmp:
            for arg in (["--seconds", "31"], ["--seconds", "0"],
                        ["--threads", "8"], ["--threads", "0"],
                        ["--timeout", "901"], ["--timeout", "0"]):
                with self.subTest(arg=arg):
                    with patch("sys.stderr"):
                        with self.assertRaises(SystemExit) as error:
                            benchmark.parse_args([*arg, "--workdir", tmp])
                        self.assertEqual(error.exception.code, 2)

    def test_probe_requires_h264_aac_and_expected_dimensions(self):
        good = {"format": {"duration": "2.0", "size": "100"},
                "streams": [{"codec_type": "video", "codec_name": "h264",
                             "width": 1280, "height": 720},
                            {"codec_type": "audio", "codec_name": "aac"}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.mp4"
            path.write_bytes(b"dummy")
            proc = type("P", (), {"stdout": json.dumps(good)})()
            with patch.object(benchmark.subprocess, "run", return_value=proc):
                parsed = benchmark.probe_video(path, 1280, 720, 2)
                self.assertEqual(parsed["duration_seconds"], 2.0)
                self.assertEqual(parsed["bytes"], 5)
            good["streams"][0]["width"] = 640
            proc.stdout = json.dumps(good)
            with patch.object(benchmark.subprocess, "run", return_value=proc):
                with self.assertRaises(RuntimeError):
                    benchmark.probe_video(path, 1280, 720, 2)


if __name__ == "__main__":
    unittest.main()
