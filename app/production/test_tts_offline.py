"""No provider calls: deterministic offline audio contract checks."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import wave

from django.test import SimpleTestCase

from .tts_offline import OfflineTtsError, save_fixture_segment


class FixtureBackend:
    def __init__(self, payload=None, crash=False):
        self.payload = payload
        self.crash = crash
        self.calls = 0

    def synthesize(self, *, text, voice_id, language):
        self.calls += 1
        if self.crash:
            raise RuntimeError("FAKE provider secret")
        if self.payload is not None:
            return self.payload
        output = BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b"\x00\x00" * 2400)
        return output.getvalue()


class OfflineTtsTests(SimpleTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def invoke(self, backend, **kwargs):
        args = dict(
            root=self.root, job_id=15, segment_index=0,
            text="Original English football story.", voice_id="DemoVoice",
            backend=backend,
        )
        args.update(kwargs)
        return save_fixture_segment(**args)

    def test_demo_wav_persisted_and_metadata_is_reusable(self):
        backend = FixtureBackend()
        with patch("urllib.request.urlopen") as request:
            first = self.invoke(backend)
            second = self.invoke(backend)
            request.assert_not_called()
        self.assertTrue(first.demo_only)
        self.assertEqual(first.provider, "offline_fixture")
        self.assertEqual(first.language, "en")
        self.assertEqual(first.path, second.path)
        self.assertEqual(first.audio_sha256, second.audio_sha256)
        self.assertAlmostEqual(first.duration_seconds, 0.1)
        self.assertTrue(Path(first.path).is_file())
        self.assertIn("jobs/15/audio/en/demo-", first.path)
        self.assertEqual(len(list(self.root.rglob("*.wav"))), 1)

    def test_invalid_text_voice_and_ids_never_call_backend(self):
        backend = FixtureBackend()
        cases = [
            {"job_id": -1}, {"job_id": True}, {"segment_index": -1},
            {"voice_id": "../escape"}, {"voice_id": ""},
            {"text": "Hello\nnew line"}, {"text": "<script>attack</script>"},
            {"text": ""}, {"text": "A" * 4001},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(
                OfflineTtsError
            ):
                self.invoke(backend, **overrides)
        self.assertEqual(backend.calls, 0)

    def test_invalid_wav_never_writes(self):
        invalid = [
            b"fake recording", b"A" * (4 * 1024 * 1024 + 1),
            b"",
        ]
        wrong_rate = BytesIO()
        with wave.open(wrong_rate, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(16000)
            out.writeframes(b"\x00\x00" * 1600)
        invalid.append(wrong_rate.getvalue())
        for payload in invalid:
            with self.subTest(size=len(payload)), self.assertRaisesMessage(
                OfflineTtsError, "invalid_audio"
            ):
                self.invoke(FixtureBackend(payload=payload))
        self.assertEqual(list(self.root.rglob("*.wav")), [])

    def test_backend_exception_is_redacted_and_no_file_written(self):
        with self.assertRaisesMessage(OfflineTtsError, "fixture_failed") as raised:
            self.invoke(FixtureBackend(crash=True))
        self.assertNotIn("FAKE provider secret", str(raised.exception))
        self.assertEqual(list(self.root.rglob("*.wav")), [])

    def test_symlink_destination_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        folder = self.root / "jobs" / "15" / "audio"
        folder.mkdir(parents=True)
        (folder / "en").symlink_to(outside, target_is_directory=True)
        # The outside folder is still within the same trusted root, so an
        # internal symlink is accepted only when it stays inside the root.
        result = self.invoke(FixtureBackend())
        self.assertTrue(Path(result.path).is_relative_to(self.root))
        other = TemporaryDirectory()
        self.addCleanup(other.cleanup)
        (folder / "en").unlink()
        (folder / "en").symlink_to(Path(other.name), target_is_directory=True)
        with self.assertRaisesMessage(OfflineTtsError, "unsafe_output_path"):
            self.invoke(FixtureBackend())
