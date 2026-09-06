import hashlib
import io
import math
import struct
import unittest
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


if __name__ == "__main__":
    unittest.main()
