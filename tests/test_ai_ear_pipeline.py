from contextlib import contextmanager
import hashlib
import io
import math
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import wave

from ai_ear.core.pipeline import AudioAnalysisError, AudioPipeline


class _MemorySink:
    def __init__(self):
        self.events = []

    def add_event(self, content, source="unknown", importance=0.6):
        self.events.append((content, source, importance))
        return f"event-{len(self.events)}"


def _sine_wav(*, frequency=440.0, sample_rate=8000, seconds=0.25, amplitude=0.5):
    frames = int(sample_rate * seconds)
    pcm = bytearray()
    for index in range(frames):
        sample = amplitude * math.sin(2.0 * math.pi * frequency * index / sample_rate)
        pcm.extend(struct.pack("<h", int(sample * 32767)))

    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(pcm))
    return output.getvalue()


def _extensible_pcm_wav():
    """Build a valid mono 16-bit WAVE_FORMAT_EXTENSIBLE PCM fixture."""
    channels = 1
    sample_rate = 8000
    bits_per_sample = 16
    block_align = channels * bits_per_sample // 8
    byte_rate = sample_rate * block_align
    pcm = struct.pack("<hhhh", 0, 8192, -8192, 0)
    pcm_subformat_guid = bytes.fromhex(
        "01000000 0000 1000 8000 00aa00389b71"
    )
    fmt = struct.pack(
        "<HHIIHHH",
        0xFFFE,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        22,
    )
    fmt += struct.pack("<HI", bits_per_sample, 0x4)
    fmt += pcm_subformat_guid

    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    chunks += b"data" + struct.pack("<I", len(pcm)) + pcm
    riff_payload = b"WAVE" + chunks
    return b"RIFF" + struct.pack("<I", len(riff_payload)) + riff_payload


class _DishonestWave:
    """Wave-like reader that returns more frames than its header declares."""

    def __init__(self):
        self._returned = False

    def getcomptype(self):
        return "NONE"

    def getnchannels(self):
        return 1

    def getframerate(self):
        return 8000

    def getsampwidth(self):
        return 2

    def getnframes(self):
        return 1

    def readframes(self, _count):
        if self._returned:
            return b""
        self._returned = True
        return struct.pack("<hh", 1, -1)


class AudioPipelineTests(unittest.TestCase):
    def setUp(self):
        self.memory = _MemorySink()
        self.pipeline = AudioPipeline(memory=self.memory)

    def test_real_wav_produces_signal_derived_deterministic_frame(self):
        payload = _sine_wav()
        first = self.pipeline.process_audio(payload)
        second = self.pipeline.process_audio(payload)

        self.assertEqual(first["schema"], "omni.ai_ear.acoustic_frame.v1")
        self.assertEqual(first["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(first["features"], second["features"])
        self.assertEqual(first["features"]["sample_rate_hz"], 8000)
        self.assertEqual(first["features"]["channels"], 1)
        self.assertEqual(first["features"]["frame_count"], 2000)
        self.assertAlmostEqual(first["features"]["duration_seconds"], 0.25, places=6)
        self.assertGreater(first["features"]["rms"], 0.30)
        self.assertGreater(first["features"]["peak"], 0.49)
        self.assertGreater(first["features"]["zero_crossing_rate"], 0.05)
        self.assertLess(first["features"]["zero_crossing_rate"], 0.2)
        self.assertTrue(first["evidence"]["input_is_real"])
        self.assertTrue(first["evidence"]["deterministic"])
        self.assertFalse(first["evidence"]["network_required"])
        self.assertEqual(len(self.memory.events), 2)
        self.assertTrue(all(event[1] == "ai_ear" for event in self.memory.events))

    def test_none_is_rejected_instead_of_fabricating_audio(self):
        with self.assertRaises(AudioAnalysisError):
            self.pipeline.process_audio(None)

    def test_listen_without_capture_adapter_fails_closed(self):
        with self.assertRaises(AudioAnalysisError):
            self.pipeline.listen()

    def test_empty_and_non_wav_payloads_are_rejected(self):
        with self.assertRaises(AudioAnalysisError):
            self.pipeline.process_audio(b"")
        with self.assertRaises(AudioAnalysisError):
            self.pipeline.process_audio(b"not-a-wave")

    def test_in_memory_resource_ceiling_is_enforced_before_parse(self):
        original = self.pipeline.MAX_IN_MEMORY_BYTES
        try:
            self.pipeline.MAX_IN_MEMORY_BYTES = 16
            with self.assertRaises(AudioAnalysisError):
                self.pipeline.process_audio(b"x" * 17)
        finally:
            self.pipeline.MAX_IN_MEMORY_BYTES = original

    def test_file_replacement_cannot_break_hash_to_analysis_binding(self):
        original_payload = _sine_wav(sample_rate=8000, seconds=0.25)
        replacement_payload = _sine_wav(sample_rate=16000, seconds=0.5)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.wav"
            path.write_bytes(original_payload)

            class _ReplacingPipeline(AudioPipeline):
                @classmethod
                @contextmanager
                def _snapshot_file(cls, source_path):
                    with super()._snapshot_file(source_path) as evidence:
                        source_path.write_bytes(replacement_payload)
                        yield evidence

            pipeline = _ReplacingPipeline(memory=self.memory)
            result = pipeline.process_audio(path)

            self.assertEqual(
                result["sha256"],
                hashlib.sha256(original_payload).hexdigest(),
            )
            self.assertEqual(result["features"]["sample_rate_hz"], 8000)
            self.assertEqual(result["features"]["frame_count"], 2000)
            self.assertEqual(path.read_bytes(), replacement_payload)

    def test_declared_sample_budget_is_rejected_before_decode(self):
        payload = _sine_wav(sample_rate=8000, seconds=0.25)

        with mock.patch.object(AudioPipeline, "MAX_DECODED_SAMPLES", 1999):
            with mock.patch.object(
                AudioPipeline,
                "_decode_pcm",
                side_effect=AssertionError("decoder must not run"),
            ) as decoder:
                with self.assertRaisesRegex(
                    AudioAnalysisError,
                    "decoded sample limit",
                ):
                    self.pipeline.process_audio(payload)

        decoder.assert_not_called()

    def test_duration_budget_is_rejected_before_decode(self):
        payload = _sine_wav(sample_rate=8000, seconds=0.25)

        with mock.patch.object(AudioPipeline, "MAX_DURATION_SECONDS", 0.1):
            with mock.patch.object(
                AudioPipeline,
                "_decode_pcm",
                side_effect=AssertionError("decoder must not run"),
            ) as decoder:
                with self.assertRaisesRegex(
                    AudioAnalysisError,
                    "duration limit",
                ):
                    self.pipeline.process_audio(payload)

        decoder.assert_not_called()

    def test_running_sample_budget_rejects_underreported_header(self):
        with mock.patch.object(AudioPipeline, "MAX_DECODED_SAMPLES", 1):
            with mock.patch.object(
                AudioPipeline,
                "_decode_pcm",
                side_effect=AssertionError("decoder must not run"),
            ) as decoder:
                with self.assertRaisesRegex(
                    AudioAnalysisError,
                    "decoded sample limit",
                ):
                    AudioPipeline._measure_wave(_DishonestWave())

        decoder.assert_not_called()

    def test_extensible_pcm_is_rejected_consistently(self):
        payload = _extensible_pcm_wav()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "extensible.wav"
            path.write_bytes(payload)

            for source in (payload, path):
                with self.subTest(source_type=type(source).__name__):
                    with self.assertRaisesRegex(
                        AudioAnalysisError,
                        "WAVE_FORMAT_EXTENSIBLE is not supported",
                    ):
                        self.pipeline.process_audio(source)


if __name__ == "__main__":
    unittest.main()
