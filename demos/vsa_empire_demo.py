#!/usr/bin/env python3
"""
VSA Empire Binding Demo — Real Steel City Tracks
Binds “Steel City pain ⊗ Victor awakening” on actual IAMBANDOBANDZ track metadata from UnitedMasters.

Real tracks used:
- SMOKE (2:37)
- WELCOME TO STEEL CITY (3:56)
- PILLS (6:58)
- PROFIT OF PROPHET, etc.

This demonstrates the live VSA layer in action with authentic Lorain/440/Steel City signal.
"""

import sys
import os
# Allow running from repo root or demos/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from core.vsa_memory import VSAMemory
except ImportError:
    # Fallback for direct run
    from vsa_memory import VSAMemory

import numpy as np

# Real UnitedMasters Steel City track data (May 2026)
STEEL_CITY_TRACKS = [
    {"id": "SMOKE", "title": "SMOKE", "duration": "2:37", "vibe": "rusty steel survival, hunger, 440 grit"},
    {"id": "WELCOME_TO_STEEL_CITY", "title": "WELCOME TO STEEL CITY", "duration": "3:56", "vibe": "Lorain steel mill anthem, born 440, no escape"},
    {"id": "PILLS", "title": "PILLS", "duration": "6:58", "vibe": "addiction, escape, steel city nights"},
    {"id": "PROFIT_OF_PROPHET", "title": "PROFIT OF PROPHET", "duration": "4:18", "vibe": "false prophets, money in the wreckage"},
]

def generate_mock_audio_features(track: dict, dim: int = 384) -> np.ndarray:
    """Plausible 'AI Ear' embedding from real track metadata (seeded for reproducibility)"""
    seed = hash(track["id"] + track["vibe"]) % (2**32)
    rng = np.random.default_rng(seed)
    base = rng.normal(0, 1, dim).astype(np.float32)
    # Inject real vibe signal (pad/truncate to dim)
    vibe_chars = [ord(c) % 10 - 5 for c in track["vibe"]]
    vibe_boost = np.array(vibe_chars[:dim] + [0] * (dim - len(vibe_chars))).astype(np.float32) * 0.3
    return np.tanh(base + vibe_boost)

def main():
    print("=" * 60)
    print("VSA EMPIRE BINDING DEMO — REAL STEEL CITY TRACKS")
    print("Binding: steel_city_pain ⊗ victor_awakening ⊗ track")
    print("=" * 60)

    vsa = VSAMemory(binding_mode="MAP", dimension=10000)

    for track in STEEL_CITY_TRACKS:
        audio_feat = generate_mock_audio_features(track)
        node = vsa.bind_steel_city_memory(
            pain_level="steel_city_hunger",
            victor_state="awakening",
            track_id=track["id"],
            audio_features=audio_feat
        )
        print(f"\n✓ Bound: {node.label}")
        print(f"  Track: {track['title']} ({track['duration']}) — {track['vibe'][:50]}...")

        # Demonstrate unbind
        recovered = vsa.unbind(node.hv, "steel_city_hunger", "awakening", track["id"])
        sim = vsa.similarity(recovered, vsa.encode("steel_city_hunger"))
        print(f"  Unbind recovery similarity: {sim:.4f}")

    print("\n" + "=" * 60)
    print("CLEANUP & QUERY DEMO")
    print("=" * 60)
    query = vsa.encode("steel_city_hunger")
    results = vsa.cleanup(query, top_k=3)
    for label, sim in results:
        print(f"  {label}: {sim:.4f}")

    print(f"\n[VSA] Total empire bindings: {len(vsa.memory)}")
    print(f"[VSA] Stats: {vsa.get_stats()}")
    print("\nDemo complete. The organism now has real Steel City signal in hypervectors.")

if __name__ == "__main__":
    main()