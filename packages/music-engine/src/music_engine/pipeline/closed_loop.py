"""Generate -> hear -> score -> rank -> manifest."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from audio_ear.scoring.bandorank import EarMetrics, ScoreBreakdown, calculate_bando_score
from ..generators.base import GenerationCandidate, GeneratorAdapter
from ..manifest import canonical_json_hash, sha256_file, write_json_atomic


class CandidateEvaluator(Protocol):
    def evaluate(self, audio_path: Path, song_plan: Mapping[str, Any]) -> EarMetrics: ...


@dataclass(frozen=True)
class RankedCandidate:
    candidate: GenerationCandidate
    metrics: EarMetrics
    score: ScoreBreakdown
    audio_sha256: str
    manifest_path: Path


@dataclass(frozen=True)
class ClosedLoopResult:
    winner: RankedCandidate
    ranked: tuple[RankedCandidate, ...]
    run_manifest_path: Path


class ClosedLoopRunner:
    def __init__(self, generator: GeneratorAdapter, evaluator: CandidateEvaluator, *, score_weights: Mapping[str, float] | None = None) -> None:
        self.generator = generator
        self.evaluator = evaluator
        self.score_weights = dict(score_weights) if score_weights is not None else None

    def run(self, song_plan: Mapping[str, Any], *, count: int = 4, seed: int = 42, output_dir: Path | str = Path("artifacts/closed-loop")) -> ClosedLoopResult:
        if count < 1:
            raise ValueError("count must be >= 1")
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        plan_hash = canonical_json_hash(song_plan)
        generated = self.generator.generate_batch(song_plan, count=count, seed=seed)
        if len(generated) != count:
            raise RuntimeError(f"Generator returned {len(generated)} candidates; expected exactly {count}")
        seen_seeds: set[int] = set()
        ranked: list[RankedCandidate] = []
        for candidate in generated:
            if candidate.seed in seen_seeds:
                raise RuntimeError(f"Generator returned duplicate seed {candidate.seed}")
            seen_seeds.add(candidate.seed)
            if not candidate.audio_path.exists() or candidate.audio_path.stat().st_size == 0:
                raise FileNotFoundError(f"Candidate missing or empty: {candidate.audio_path}")
            metrics = self.evaluator.evaluate(candidate.audio_path, song_plan)
            score = calculate_bando_score(metrics, self.score_weights)
            audio_hash = sha256_file(candidate.audio_path)
            manifest_path = out_dir / f"candidate_{candidate.seed}.bandorank.json"
            write_json_atomic(manifest_path, {"schema_version": "bando.candidate-manifest.v0.1", "song_plan_sha256": plan_hash, "audio_sha256": audio_hash, "audio_path": str(candidate.audio_path), "seed": candidate.seed, "adapter": {"id": candidate.adapter_id, "revision": candidate.adapter_revision, "metadata": dict(candidate.metadata)}, "ear_metrics": asdict(metrics), "bandorank": score.to_dict()})
            ranked.append(RankedCandidate(candidate, metrics, score, audio_hash, manifest_path))
        ranked.sort(key=lambda item: (-item.score.total, item.candidate.seed, str(item.candidate.audio_path)))
        winner = ranked[0]
        run_manifest_path = out_dir / "run_manifest.json"
        write_json_atomic(run_manifest_path, {"schema_version": "bando.closed-loop-run.v0.1", "song_plan_sha256": plan_hash, "generator": {"id": self.generator.adapter_id, "revision": self.generator.adapter_revision, "capabilities": sorted(self.generator.capabilities)}, "requested": {"count": count, "base_seed": seed}, "winner": {"seed": winner.candidate.seed, "audio_path": str(winner.candidate.audio_path), "audio_sha256": winner.audio_sha256, "score": winner.score.total, "candidate_manifest": str(winner.manifest_path)}, "ranking": [{"rank": i + 1, "seed": item.candidate.seed, "audio_path": str(item.candidate.audio_path), "audio_sha256": item.audio_sha256, "score": item.score.total, "candidate_manifest": str(item.manifest_path)} for i, item in enumerate(ranked)]})
        return ClosedLoopResult(winner, tuple(ranked), run_manifest_path)
