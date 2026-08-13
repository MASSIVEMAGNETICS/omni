from __future__ import annotations

import unittest

from audio_ear.scoring.bandorank import EarMetrics, calculate_bando_score, normalized_tempo_delta


class BandoRankTests(unittest.TestCase):
    def test_half_double_tempo_equivalence(self) -> None:
        self.assertAlmostEqual(normalized_tempo_delta(86.0, 172.0), 0.0)
        self.assertAlmostEqual(normalized_tempo_delta(172.0, 86.0), 0.0)

    def test_artifacts_reduce_score(self) -> None:
        base = dict(
            target_bpm=86.0,
            detected_bpm=86.0,
            key_score=1.0,
            energy_score=1.0,
            fidelity_score=1.0,
            lyric_alignment_score=1.0,
        )
        clean = calculate_bando_score(EarMetrics(**base, artifact_score=0.0))
        dirty = calculate_bando_score(EarMetrics(**base, artifact_score=1.0))
        self.assertGreater(clean.total, dirty.total)
        self.assertAlmostEqual(clean.total, 1.0)

    def test_metric_validation_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            EarMetrics(
                target_bpm=86.0,
                detected_bpm=86.0,
                key_score=1.2,
                energy_score=1.0,
                fidelity_score=1.0,
                lyric_alignment_score=1.0,
            )


if __name__ == "__main__":
    unittest.main()
