from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path
from typing import Any, Mapping

from audio_ear.scoring.bandorank import EarMetrics
from music_engine.generators.base import GenerationCandidate, GeneratorAdapter
from music_engine.pipeline.closed_loop import ClosedLoopRunner


def _write_silence_wav(path: Path, frames: int = 800) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\x00\x00" * frames)


class FakeGenerator(GeneratorAdapter):
    adapter_id = "fake"
    adapter_revision = "test"
    def __init__(self, root: Path) -> None: self.root = root
    @property
    def capabilities(self) -> frozenset[str]: return frozenset({"generate"})
    def generate_batch(self, song_plan: Mapping[str, Any], count: int = 4, seed: int = 42) -> list[GenerationCandidate]:
        output = []
        for index in range(count):
            candidate_seed = seed + index
            path = self.root / f"{candidate_seed}.wav"; _write_silence_wav(path)
            output.append(GenerationCandidate(path, candidate_seed, self.adapter_id, self.adapter_revision))
        return output
    def repaint(self, audio_path: Path, mask_start_sec: float, mask_end_sec: float, prompt: str, *, seed: int = 42) -> GenerationCandidate: raise NotImplementedError


class FakeEvaluator:
    def evaluate(self, audio_path: Path, song_plan: Mapping[str, Any]) -> EarMetrics:
        seed = int(audio_path.stem); quality = 0.9 if seed % 2 == 0 else 0.5
        return EarMetrics(86.0, 172.0, quality, quality, quality, quality, 0.0)


class ClosedLoopTests(unittest.TestCase):
    def test_runner_ranks_and_writes_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = ClosedLoopRunner(FakeGenerator(root), FakeEvaluator()).run({"bpm": 86, "key": "D minor", "lyrics": "test"}, count=4, seed=440, output_dir=root / "manifest")
            self.assertEqual(result.winner.candidate.seed, 440)
            self.assertTrue(result.run_manifest_path.exists())
            self.assertEqual(len(result.ranked), 4)
            self.assertTrue(all(item.manifest_path.exists() for item in result.ranked))


if __name__ == "__main__": unittest.main()
