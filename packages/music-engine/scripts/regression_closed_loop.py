#!/usr/bin/env python3
"""Run the first live SongPlan -> ACE-Step -> AI Ear -> BandoRank regression."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
for package_src in (REPO_ROOT / "packages" / "audio-ear" / "src", REPO_ROOT / "packages" / "music-engine" / "src"):
    sys.path.insert(0, str(package_src))

from music_engine.evaluation.ai_ear_client import AiEarEvaluator
from music_engine.generators.ace_step_adapter import AceStepAdapter
from music_engine.pipeline.closed_loop import ClosedLoopRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("song_plan", type=Path, help="Path to SongPlan JSON")
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--seed", type=int, default=440)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/closed-loop"))
    parser.add_argument("--ace-url", default=os.getenv("BANDO_ACE_URL", "http://127.0.0.1:8001"))
    parser.add_argument("--ear-url", default=os.getenv("BANDO_EAR_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--ace-api-key", default=os.getenv("ACESTEP_API_KEY"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.count < 1:
        raise SystemExit("--count must be >= 1")
    try:
        song_plan = json.loads(args.song_plan.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not load SongPlan {args.song_plan}: {exc}") from exc
    if not isinstance(song_plan, dict):
        raise SystemExit("SongPlan JSON must be an object")
    generator = AceStepAdapter(base_url=args.ace_url, output_dir=args.output_dir / "ace", api_key=args.ace_api_key)
    evaluator = AiEarEvaluator(base_url=args.ear_url)
    result = ClosedLoopRunner(generator, evaluator).run(song_plan, count=args.count, seed=args.seed, output_dir=args.output_dir)
    print(f"WINNER_WAV={result.winner.candidate.audio_path}")
    print(f"BANDORANK_SCORE={result.winner.score.total:.6f}")
    print(f"MANIFEST={result.run_manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
