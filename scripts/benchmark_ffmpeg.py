#!/usr/bin/env python3
"""Small, isolated FFmpeg sizing probe for FootballStudio (FS-003b / #7).

Generates only artificial test video and a sine-wave audio track, never reads
existing media, never touches Docker or the network, and cleans temporary files.
Run on an authorized test host or inside the eventual worker container.
A pass here does NOT prove the complete 8–10 minute film pipeline will fit.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


RESOLUTIONS = {"720p": (1280, 720), "1080p": (1920, 1080)}
FRAME_RATE = 24
AUDIO_RATE = 128_000


def estimate_encoded_bytes(seconds: int, video_mbps: float, audio_kbps: int = 128) -> int:
    """Bitrate-only planning estimate; excludes container overhead and intermediates."""
    if seconds <= 0 or video_mbps <= 0 or audio_kbps < 0:
        raise ValueError("Expected positive seconds/video bitrate and nonnegative audio rate")
    return int(seconds * (video_mbps * 1_000_000 + audio_kbps * 1_000) / 8)


def read_rss_kib(pid: int) -> int | None:
    """Sample VmRSS on Linux; this is not an exact high-watermark."""
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, IndexError, ValueError):
        pass
    return None


def command_for(width: int, height: int, seconds: int, threads: int, dest: Path) -> list[str]:
    return [
        "ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate={FRAME_RATE}",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", str(seconds), "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "23",
        "-threads", str(threads), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(dest),
    ]


def probe_video(path: Path, width: int, height: int, seconds: int) -> dict:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,size:stream=codec_type,codec_name,width,height",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True, timeout=20,
    )
    meta = json.loads(probe.stdout)
    video = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in meta.get("streams", []) if s.get("codec_type") == "audio"), None)
    duration = float(meta.get("format", {}).get("duration", 0))
    if not video or video.get("width") != width or video.get("height") != height:
        raise RuntimeError("Output resolution differs from requested profile")
    if video.get("codec_name") != "h264" or not audio or audio.get("codec_name") != "aac":
        raise RuntimeError("Output must have H.264 video and AAC audio")
    if abs(duration - seconds) > 0.5:
        raise RuntimeError("Output duration is outside allowed smoke-test tolerance")
    return {"duration_seconds": duration, "bytes": path.stat().st_size,
            "video_codec": video["codec_name"], "audio_codec": audio["codec_name"]}


def run_one(label: str, seconds: int, threads: int, directory: Path,
            timeout_seconds: int) -> dict:
    width, height = RESOLUTIONS[label]
    output = directory / f"{label}.mp4"
    cmd = command_for(width, height, seconds, threads, output)
    started = time.monotonic()
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    peak_rss = None
    while process.poll() is None:
        rss = read_rss_kib(process.pid)
        if rss is not None:
            peak_rss = max(peak_rss or 0, rss)
        if time.monotonic() - started > timeout_seconds:
            process.kill()
            process.communicate()
            raise RuntimeError(f"{label} FFmpeg exceeded {timeout_seconds}s timeout")
        time.sleep(0.025)
    _, stderr = process.communicate()
    wall_seconds = round(time.monotonic() - started, 3)
    if process.returncode:
        # Do not print a command containing paths from the private host.
        message = stderr.decode("utf-8", errors="replace")[-600:]
        raise RuntimeError(f"{label} FFmpeg returned {process.returncode}: {message}")
    meta = probe_video(output, width, height, seconds)
    return {
        "profile": label, "width": width, "height": height,
        "fps": FRAME_RATE, "threads": threads,
        "wall_seconds": wall_seconds,
        "sampled_peak_ffmpeg_rss_kib": peak_rss,
        "output": meta,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=5,
                        help="Artificial clip duration, 1–30 seconds (default 5)")
    parser.add_argument("--threads", type=int, default=2,
                        help="FFmpeg encoding threads, 1–4 (default 2)")
    parser.add_argument("--profile", choices=["both", "720p", "1080p"], default="both")
    parser.add_argument("--workdir", type=Path, default=Path(tempfile.gettempdir()),
                        help="Existing writable folder to measure, ideally the worker's data volume")
    parser.add_argument("--timeout", type=int, default=180,
                        help="Maximum wallclock time per clip, 5–900 seconds")
    args = parser.parse_args(argv)
    if not 1 <= args.seconds <= 30:
        parser.error("--seconds must be 1–30")
    if not 1 <= args.threads <= 4:
        parser.error("--threads must be 1–4")
    if not 5 <= args.timeout <= 900:
        parser.error("--timeout must be 5–900")
    if not args.workdir.is_dir() or not os.access(args.workdir, os.W_OK):
        parser.error("--workdir must exist and be writable")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    for binary in ("ffmpeg", "ffprobe"):
        if not shutil.which(binary):
            print(f"Cannot run: {binary} missing", file=sys.stderr)
            return 2
    before = shutil.disk_usage(args.workdir)
    results = []
    selected = list(RESOLUTIONS) if args.profile == "both" else [args.profile]
    try:
        with tempfile.TemporaryDirectory(prefix="footballstudio-sizing-", dir=args.workdir) as tmp:
            for label in selected:
                results.append(run_one(label, args.seconds, args.threads,
                                       Path(tmp), args.timeout))
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"Benchmark failed: {exc}", file=sys.stderr)
        return 1
    report = {
        "kind": "synthetic_ffmpeg_benchmark_not_full_movie",
        "is_vps_measurement": False,  # Change only with separate, verified VPS run report.
        "environment": "current_machine_set_explicitly_by_operator",
        "test_seconds_per_profile": args.seconds,
        "workdir_free_bytes_before": before.free,
        "profiles": results,
        "limitations": [
            "These clips use generated patterns, not real images, captions or scene transitions.",
            "Process VmRSS is sampled, not a guaranteed peak memory measurement.",
            "This report does not include Django, PostgreSQL, TTS, downloaded media, backups or other VPS services.",
            "Only the operator can attest that execution occurred on the target VPS.",
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
