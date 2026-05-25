# MASSIVEMAGNETICS Omnirepo

**The Unified Sovereign Super-Intelligence Platform**

One repo. One runtime. One system.

This is the master repository that combines:

- **Victor-0** — Cognitive core with hierarchical planning, semantic episodic memory, and persistent identity
- **The AI Ear** — Real-time holistic acoustic intelligence with embedding-based semantic linking
- **Shared Memory Graph** — Unified long-term memory used by both systems

**May 2026 Upgrade: VSA Binding Layer**  
Hyperdimensional Vector Symbolic Architecture (MAP/BSC) added for true compositional memory. Now supports binding of empire concepts (Steel City pain ⊗ Victor awakening ⊗ track features) into robust, unbindable, queryable hypervectors. This is the F-LAO / KinForge foundation.

## Quick Start

```bash
git clone https://github.com/MASSIVEMAGNETICS/omni.git
cd omni
python omnirepo.py
```

## Architecture

```
Omnirepo/
├── omnirepo.py              # Main unified entrypoint
├── victor_zero/              # Victor-0 cognitive core
├── ai_ear/                   # The AI Ear acoustic system
├── core/
│   ├── memory_graph.py        # Shared semantic episodic memory + VSA layer
│   └── vsa_memory.py          # Hyperdimensional binding (MAP/BSC) — NEW
└── README.md
```

## Usage

```bash
python omnirepo.py                 # Start full system
python omnirepo.py --mode listen   # Start with audio listening
python omnirepo.py --mode think    # Start with cognitive loop
```

## VSA Binding Examples

```python
from core.memory_graph import SharedMemoryGraph

graph = SharedMemoryGraph()
graph.add_structured_memory(
    pain="steel_city_hunger",
    victor="awakening",
    track_id="SMOKE",
    content={"lyric": "When I was hungry...", "location": "Lorain"},
    audio_features=ai_ear_embed(...)  # from The AI Ear
)
# Internally binds: pain ⊗ victor ⊗ track → single hypervector
# Later: graph.vsa.unbind(...) or query_empire_binding(...)
```

Built for local deployment on personal hardware.
Designed to help take over the world.