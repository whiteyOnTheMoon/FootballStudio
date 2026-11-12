"""FS-018a offline TTS artifact contract. No cloud provider, network or billing.

Accept only a trusted *fixture* synth adapter. The returned audio is inspected
as bounded mono 24-kHz PCM WAV and saved atomically into a private location.
The resulting file is DEMO audio, never a voiceover or completed film.
"""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import re
import tempfile
import wave


class OfflineTtsError(ValueError):
    """Only short stable error codes; do not disclose adapter details."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class OfflineAudioArtifact:
    path: str
    input_sha256: str
    audio_sha256: str
    duration_seconds: float
    bytes_written: int
    voice_id: str
    language: str = "en"
    provider: str = "offline_fixture"
    demo_only: bool = True


_VOICE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_MAX_WAV_BYTES = 4 * 1024 * 1024
_MAX_TEXT = 4000


def _checked_wav(data):
    if not isinstance(data, bytes) or not 44 <= len(data) <= _MAX_WAV_BYTES:
        raise OfflineTtsError("invalid_audio")
    try:
        with wave.open(BytesIO(data), "rb") as reader:
            channels = reader.getnchannels()
            rate = reader.getframerate()
            width = reader.getsampwidth()
            frames = reader.getnframes()
            encoding = reader.getcomptype()
            consumed = reader.readframes(frames)
    except (EOFError, OSError, ValueError, wave.Error):
        raise OfflineTtsError("invalid_audio") from None
    if (
        channels != 1 or rate != 24000 or width != 2
        or encoding != "NONE" or frames < 1
        or len(consumed) != frames * 2
        or not 0.01 <= frames / rate <= 90
    ):
        raise OfflineTtsError("invalid_audio")
    return frames / rate


def save_fixture_segment(*, root, job_id, segment_index, text, voice_id, backend):
    """Write only fake audio; caller is responsible for job authorization.

    No untrusted output path is accepted: all destination names are derived
    from numeric identifiers and a SHA-256 fingerprint. No retry on failure.
    root must be a trusted, private application directory, never a web root.
    """
    if (
        type(job_id) is not int or job_id <= 0
        or type(segment_index) is not int or not 0 <= segment_index < 10000
        or not isinstance(text, str) or not 2 <= len(text) <= _MAX_TEXT
        or not text.strip() or not text.isprintable()
        or any(ch in text for ch in "<>\r\n\t")
        or not isinstance(voice_id, str) or not _VOICE.fullmatch(voice_id)
        or not callable(getattr(backend, "synthesize", None))
    ):
        raise OfflineTtsError("invalid_request")
    if not isinstance(root, (str, Path)) or not str(root):
        raise OfflineTtsError("invalid_root")

    digest = sha256(("en\0" + voice_id + "\0" + text).encode("utf-8")).hexdigest()
    try:
        audio = backend.synthesize(text=text, voice_id=voice_id, language="en")
    except Exception:
        raise OfflineTtsError("fixture_failed") from None
    duration = _checked_wav(audio)
    audio_digest = sha256(audio).hexdigest()

    # This file is NOT public web content. Store under the operator's private
    # directory, not STATIC_ROOT or MEDIA_URL.
    folder = Path(root) / "jobs" / str(job_id) / "audio" / "en"
    name = f"demo-{segment_index:04d}-{digest[:16]}.wav"
    temp_path = None
    try:
        # Prevent an existing directory symlink from redirecting private data.
        anchor = Path(root).resolve(strict=True)
        folder.mkdir(parents=True, exist_ok=True)
        resolved = folder.resolve(strict=True)
        if not resolved.is_relative_to(anchor):
            raise OfflineTtsError("unsafe_output_path")
        target = resolved / name
        if target.is_symlink():
            raise OfflineTtsError("unsafe_output_path")
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".tts-fixture-", suffix=".tmp",
            dir=resolved, delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(audio)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
        temp_path = None
    except OfflineTtsError:
        raise
    except (OSError, ValueError):
        raise OfflineTtsError("artifact_write_failed") from None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return OfflineAudioArtifact(
        path=str(target), input_sha256=digest, audio_sha256=audio_digest,
        duration_seconds=duration, bytes_written=len(audio), voice_id=voice_id,
    )
