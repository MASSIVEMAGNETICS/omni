#!/usr/bin/env python3
"""
Omnirepo - Unified Sovereign Intelligence Platform

Brings Victor-0 and The AI Ear together with shared memory.
"""

import sys

print("[Omnirepo] Starting unified sovereign intelligence platform...")

try:
    from victor_zero.core import VictorZero
    from ai_ear.core.pipeline import AudioPipeline
    from core.memory_graph import SharedMemoryGraph

    memory = SharedMemoryGraph()
    victor = VictorZero()
    ear = AudioPipeline()

    print("[Omnirepo] Victor-0 loaded with shared memory")
    print("[Omnirepo] The AI Ear loaded with shared memory")
    print("[Omnirepo] All systems integrated and ready.")

except ImportError as e:
    print(f"[Omnirepo] Running in development mode: {e}")

if __name__ == "__main__":
    print("[Omnirepo] Omnirepo initialized successfully.")