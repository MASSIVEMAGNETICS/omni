# Bando Sovereign Audio Packages — Phase 1

This directory is the merge-safe migration target for the sovereign music stack. Existing top-level code remains untouched until the new loop proves itself.

## Current Phase 1 packages

- `audio-ear/` — deterministic BandoRank critic contract.
- `music-engine/` — disposable generator adapters, AI Ear evaluation bridge, immutable manifests, and closed-loop ranking.
- `song-mind/` — reserved migration target for Song Bloom cognition/BMIR.
- `voice/` — reserved migration target for consent-safe voice identity.

## External repo disposition

No external repositories are mutated by this branch.

| Repository | Phase 1 status |
|---|---|
| `MASSIVEMAGNETICS/ACE-Step-1.5` | PRIMARY_GENERATOR_ORGAN |
| `MASSIVEMAGNETICS/the-ai-ear` | PRIMARY_CRITIC_SERVICE |
| `MASSIVEMAGNETICS/Song-Bloom-Bando-fied-Edition` | HARVEST_COGNITION |
| `MASSIVEMAGNETICS/SUNOKILLER` | HARVEST_ONLY / R&D |
| `MASSIVEMAGNETICS/audio-gen` | ARCHIVE_CANDIDATE |
| `MASSIVEMAGNETICS/victor-suno-godcore` | ARCHIVE_CANDIDATE |

Archive candidates should only be archived after the closed-loop regression passes, so rollback remains trivial.

## Install for development

```bash
python -m pip install -e packages/audio-ear
python -m pip install -e packages/music-engine
```

No third-party runtime dependency is added by these two packages. Live generation and evaluation call the already-local ACE-Step and AI Ear HTTP services.

## Run unit tests

```bash
PYTHONPATH="packages/audio-ear/src:packages/music-engine/src" \
  python -m unittest discover -s packages/audio-ear/tests -p "test_*.py"

PYTHONPATH="packages/audio-ear/src:packages/music-engine/src" \
  python -m unittest discover -s packages/music-engine/tests -p "test_*.py"
```

On Windows PowerShell:

```powershell
$env:PYTHONPATH="packages/audio-ear/src;packages/music-engine/src"
python -m unittest discover -s packages/audio-ear/tests -p "test_*.py"
python -m unittest discover -s packages/music-engine/tests -p "test_*.py"
```

## Live first-loop regression

1. Start ACE-Step's verified API:

```bash
cd ../ACE-Step-1.5
uv run acestep-api
```

2. Start `the-ai-ear` API on port 8080.

3. From `omni`, run:

```bash
python packages/music-engine/scripts/regression_closed_loop.py \
  packages/music-engine/examples/song_plan_86bpm.json \
  --count 4 \
  --seed 440
```

The regression exits non-zero on missing audio, unavailable services, invalid JSON, evaluation failure, or malformed metrics. Successful output prints:

```text
WINNER_WAV=...
BANDORANK_SCORE=...
MANIFEST=...
```
