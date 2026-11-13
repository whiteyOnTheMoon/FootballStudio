"""FS-020: offline, *synthetic* render-engine smoke test.

This verifies the actual worker runtime can synthesize a neutral English test
sentence, encode H.264/AAC and validate an MP4 with ffprobe. It does NOT use
research, club names, user uploads, licensed external material or the
unapproved documentary draft. It is not an exported film and must never mark
a ProductionJob completed.

All test assets are original and generated on demand. Each invocation uses a
private temporary directory, deletes it upon exit and never connects to a
network or invokes a shell. No path/voice/text arguments from HTTP or users.
"""
import json
import math
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory


_TEST_SPEECH = (
    "This is a FootballStudio local production pipeline test. "
    "It is not a football documentary, and it contains no researched claims."
)
_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_MAX_AUDIO_BYTES = 2_000_000
_MAX_VIDEO_BYTES = 8_000_000
_VIDEO_SIZE = (960, 540)


class RenderEngineError(Exception):
    """Safe, bounded failure string without raw command output."""


def _tools():
    binaries = {}
    for program in ("ffmpeg", "ffprobe", "espeak-ng"):
        value = shutil.which(program)
        if not value:
            raise RenderEngineError(f"missing_required_binary:{program}")
        binaries[program] = value
    if not _FONT.is_file():
        raise RenderEngineError("missing_original_graphics_font")
    return binaries


def inspect_render_stack():
    """A read-only prerequisite check, not evidence that encoding works."""
    _tools()
    return {
        "available": True,
        "video_codec_target": "h264",
        "audio_codec_target": "aac",
        "voice_engine": "espeak-ng",
        "offline_only": True,
        "feature_stage": "synthetic_pipeline_test",
        "documentary_renderer_ready": False,
    }


def _execute(args, *, timeout, input_data=None):
    try:
        done = subprocess.run(
            args,
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RenderEngineError("tool_timeout") from exc
    except OSError as exc:
        raise RenderEngineError("tool_launch_failed") from exc
    if done.returncode != 0:
        # Do not leak command stderr or original filenames into response/log.
        raise RenderEngineError("tool_execution_failed")
    return done.stdout


def _video_filter():
    # Fixed author-owned wording only: no untrusted user text can enter
    # FFmpeg filter arguments, filesystem paths, or dynamic shell commands.
    base = f"fontfile={_FONT}"
    return ",".join((
        f"drawtext={base}:fontcolor=white:text='FootballStudio':fontsize=58:"
        "x=(w-text_w)/2:y=(h-text_h)/2-65",
        f"drawtext={base}:fontcolor=white:text='LOCAL RENDER TEST':fontsize=29:"
        "x=(w-text_w)/2:y=(h-text_h)/2+26",
        f"drawtext={base}:fontcolor=0x9acac5:text='Synthetic media only':fontsize=19:"
        "x=(w-text_w)/2:y=(h-text_h)/2+83",
    ))


def run_synthetic_render_smoke():
    """Create, inspect and delete a short *non-documentary* MP4 test.

    Success proves only that local TTS + encoding + container runtime work.
    The actual video remains unavailable until a compliant documentary
    script/media/license/voice pipeline is integrated and independently gated.
    """
    tools = _tools()
    with TemporaryDirectory(prefix="fs-render-check-") as folder:
        root = Path(folder)
        wav = root / "synthetic-voice.wav"
        mp4 = root / "synthetic-test.mp4"
        voice = _execute(
            [
                tools["espeak-ng"], "--stdout", "-v", "en-us",
                "-s", "145", "--stdin",
            ],
            input_data=_TEST_SPEECH.encode("utf-8"),
            timeout=15,
        )
        if (
            not voice.startswith(b"RIFF") or voice[8:12] != b"WAVE"
            or not 512 <= len(voice) <= _MAX_AUDIO_BYTES
        ):
            raise RenderEngineError("invalid_synthetic_voice")
        wav.write_bytes(voice)

        _execute([
            tools["ffmpeg"], "-hide_banner", "-loglevel", "error",
            "-nostdin", "-y",
            "-f", "lavfi", "-i", "color=c=0x0b1320:s=960x540:r=24",
            "-i", str(wav),
            "-vf", _video_filter(),
            "-c:v", "libx264", "-threads", "2", "-preset", "ultrafast",
            "-crf", "30", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k",
            "-t", "10", "-shortest", "-movflags", "+faststart",
            str(mp4),
        ], timeout=45)

        if not mp4.is_file():
            raise RenderEngineError("missing_mp4")
        size = mp4.stat().st_size
        if not 1024 <= size <= _MAX_VIDEO_BYTES:
            raise RenderEngineError("invalid_mp4_size")
        with mp4.open("rb") as stream:
            signature = stream.read(12)
        if signature[4:8] != b"ftyp":
            raise RenderEngineError("invalid_mp4_header")

        raw = _execute([
            tools["ffprobe"], "-v", "error",
            "-show_entries",
            "format=duration:stream=codec_name,codec_type,width,height",
            "-of", "json", str(mp4),
        ], timeout=10)
        try:
            data = json.loads(raw.decode("utf-8"))
            streams = data["streams"]
            video = next(s for s in streams if s["codec_type"] == "video")
            audio = next(s for s in streams if s["codec_type"] == "audio")
            seconds = float(data["format"]["duration"])
        except (ValueError, KeyError, TypeError, UnicodeError, StopIteration) as exc:
            raise RenderEngineError("invalid_probe_response") from exc
        if (
            video.get("codec_name") != "h264"
            or audio.get("codec_name") != "aac"
            or (video.get("width"), video.get("height")) != _VIDEO_SIZE
            or not math.isfinite(seconds)
            or not 0.8 <= seconds <= 10.1
        ):
            raise RenderEngineError("unexpected_media_streams")

        return {
            "passed": True,
            "mode": "original_synthetic_render_smoke_only",
            "duration_seconds": round(seconds, 2),
            "width": video["width"],
            "height": video["height"],
            "video_codec": "h264",
            "audio_codec": "aac",
            "size_bytes": size,
            "voice_engine": "espeak-ng",
            "network_calls": 0,
            "paid_api_calls": 0,
            "retained_files": 0,
            "documentary_completed": False,
        }
