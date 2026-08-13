"""Deterministic multi-objective scoring for generated music candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Mapping

SCHEMA_VERSION = "bandorank.v0.1"

DEFAULT_WEIGHTS: dict[str, float] = {
    "bpm": 0.20,
    "key": 0.15,
    "energy": 0.15,
    "fidelity": 0.25,
    "lyrics": 0.25,
    "artifact_penalty": 0.30,
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def normalized_tempo_delta(target_bpm: float, detected_bpm: float) -> float:
    """Return the smallest BPM error accounting for common half/double-tempo ambiguity."""
    if not (isfinite(target_bpm) and isfinite(detected_bpm)):
        raise ValueError("BPM values must be finite")
    if target_bpm <= 0.0 or detected_bpm <= 0.0:
        raise ValueError("BPM values must be positive")
    candidates = (
        detected_bpm / 4.0,
        detected_bpm / 2.0,
        detected_bpm,
        detected_bpm * 2.0,
        detected_bpm * 4.0,
    )
    return min(abs(target_bpm - candidate) for candidate in candidates)


@dataclass(frozen=True)
class EarMetrics:
    """Normalized critic measurements.

    Scores are in [0, 1]. artifact_score uses 0=clean, 1=severe artifacts.
    """

    target_bpm: float
    detected_bpm: float
    key_score: float
    energy_score: float
    fidelity_score: float
    lyric_alignment_score: float
    artifact_score: float = 0.0

    def __post_init__(self) -> None:
        normalized_tempo_delta(self.target_bpm, self.detected_bpm)
        for name in (
            "key_score",
            "energy_score",
            "fidelity_score",
            "lyric_alignment_score",
            "artifact_score",
        ):
            value = getattr(self, name)
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1], got {value!r}")


@dataclass(frozen=True)
class ScoreBreakdown:
    schema_version: str
    total: float
    components: dict[str, float]
    penalties: dict[str, float]
    weights: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def calculate_bando_score(
    metrics: EarMetrics,
    weights: Mapping[str, float] | None = None,
    *,
    bpm_tolerance: float = 20.0,
) -> ScoreBreakdown:
    """Score one candidate while preserving every component for auditability."""
    if bpm_tolerance <= 0 or not isfinite(bpm_tolerance):
        raise ValueError("bpm_tolerance must be a positive finite number")

    effective = dict(DEFAULT_WEIGHTS if weights is None else weights)
    required = {"bpm", "key", "energy", "fidelity", "lyrics", "artifact_penalty"}
    missing = required.difference(effective)
    if missing:
        raise ValueError(f"Missing BandoRank weights: {sorted(missing)}")
    if any((not isfinite(float(v)) or float(v) < 0.0) for v in effective.values()):
        raise ValueError("All BandoRank weights must be finite and non-negative")

    quality_keys = ("bpm", "key", "energy", "fidelity", "lyrics")
    quality_weight_sum = sum(float(effective[k]) for k in quality_keys)
    if quality_weight_sum <= 0.0:
        raise ValueError("At least one quality weight must be positive")

    normalized_weights = {
        key: float(effective[key]) / quality_weight_sum for key in quality_keys
    }
    normalized_weights["artifact_penalty"] = float(effective["artifact_penalty"])

    bpm_delta = normalized_tempo_delta(metrics.target_bpm, metrics.detected_bpm)
    bpm_score = _clamp01(1.0 - (bpm_delta / bpm_tolerance))

    components = {
        "bpm": bpm_score,
        "key": metrics.key_score,
        "energy": metrics.energy_score,
        "fidelity": metrics.fidelity_score,
        "lyrics": metrics.lyric_alignment_score,
    }
    quality = sum(normalized_weights[k] * components[k] for k in quality_keys)
    artifact_penalty = normalized_weights["artifact_penalty"] * metrics.artifact_score
    total = _clamp01(quality - artifact_penalty)

    return ScoreBreakdown(
        schema_version=SCHEMA_VERSION,
        total=total,
        components=components,
        penalties={"artifact": artifact_penalty},
        weights=normalized_weights,
    )
