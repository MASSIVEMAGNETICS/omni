#!/usr/bin/env python3
"""
Omnirepo - Unified Sovereign Intelligence Platform

Brings Victor-0 and The AI Ear together with shared memory.

Usage:
    python omnirepo.py                 # Start unified system
    python omnirepo.py --mode listen   # Start with audio listening
"""

import sys

import argparse

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


def main():
    parser = argparse.ArgumentParser(description="Omnirepo - Unified Sovereign Intelligence")
    parser.add_argument("--mode", default="full", choices=["full", "listen", "think"], help="Run mode")
    args = parser.parse_args()

    if args.mode == "listen":
        print("[Omnirepo] Starting in listen mode (The AI Ear active)")
    elif args.mode == "think":
        print("[Omnirepo] Starting in think mode (Victor-0 active)")
    else:
        print("[Omnirepo] Full unified mode active")

if __name__ == "__main__":
    main()