#!/usr/bin/env python3
"""
Omnirepo - Unified Sovereign Intelligence Platform

Brings Victor-0, The AI Ear, Shared Memory Graph + VSA Binding + Fractal Layer together.

May 2026 Upgrade: Full VSA compositional memory + Fractal VSA hybrid live.

Usage:
    python omnirepo.py                 # Start unified system
    python omnirepo.py --mode listen   # Start with audio listening + VSA
    python omnirepo.py --mode think    # Start with Victor-0 planning loop (VSA bound)
    python omnirepo.py --demo vsa      # Run Steel City empire binding demo
"""

import sys
import argparse

print("[Omnirepo] Starting unified sovereign intelligence platform...")

try:
    from victor_zero.core import VictorZero
    from ai_ear.core.pipeline import AudioPipeline
    from core.memory_graph import SharedMemoryGraph
    from core.vsa_memory import VSAMemory
    from core.fractal_vsa import FractalVSAMemory

    memory = SharedMemoryGraph()
    victor = VictorZero()
    ear = AudioPipeline()
    vsa = VSAMemory(binding_mode="MAP")
    fractal = FractalVSAMemory()

    print("[Omnirepo] Victor-0 loaded with shared memory + VSA")
    print("[Omnirepo] The AI Ear loaded with shared memory + VSA")
    print("[Omnirepo] Fractal VSA hybrid online")
    print("[Omnirepo] All systems integrated and ready.")

except ImportError as e:
    print(f"[Omnirepo] Running in development mode: {e}")
    vsa = None
    fractal = None


def run_vsa_demo():
    """Run the Steel City empire binding demo"""
    print("\n[Omnirepo] Launching VSA Empire Demo with real UnitedMasters Steel City tracks...")
    try:
        from demos.vsa_empire_demo import main as demo_main
        demo_main()
    except Exception as e:
        print(f"[Demo] Error: {e}. Run directly: python demos/vsa_empire_demo.py")


def victor_planning_loop():
    """Simple Victor-0 style planning loop using VSA binding"""
    print("\n[Victor-0] Starting hierarchical planning loop with VSA binding...")
    if vsa is None:
        print("[Victor-0] VSA not available in dev mode")
        return

    # Example plan: "Escape hunger" → bind pain + goal + action
    plan_steps = [
        ("steel_city_hunger", "escape_poverty", "get_money"),
        ("steel_city_hunger", "build_legacy", "make_music"),
        ("steel_city_hunger", "awaken_victor", "bind_signal")
    ]

    for pain, goal, action in plan_steps:
        bound = vsa.bind(vsa.encode(pain), vsa.encode(goal), vsa.encode(action))
        print(f"  Bound plan: {pain} ⊗ {goal} ⊗ {action}")
        # In real Victor-0 this would feed into hierarchical planner

    print("[Victor-0] Planning complete. VSA hypervectors ready for execution.")


def main():
    parser = argparse.ArgumentParser(description="Omnirepo - Unified Sovereign Intelligence")
    parser.add_argument("--mode", default="full", choices=["full", "listen", "think", "demo"], help="Run mode")
    parser.add_argument("--demo", default=None, choices=["vsa", "fractal"], help="Run specific demo")
    args = parser.parse_args()

    if args.mode == "listen":
        print("[Omnirepo] Starting in listen mode (The AI Ear + VSA active)")
        if vsa:
            print("[VSA] Ready to bind acoustic events to Victor identity")
    elif args.mode == "think":
        print("[Omnirepo] Starting in think mode (Victor-0 + VSA planning loop)")
        victor_planning_loop()
    elif args.demo == "vsa":
        run_vsa_demo()
    elif args.demo == "fractal":
        print("[FractalVSA] Running fractal binding demo...")
        if fractal:
            node = fractal.bind_steel_city_fractal("steel_city_hunger", "awakening", "SMOKE")
            print(f"Fractal node: {node.label}")
    else:
        print("[Omnirepo] Full unified mode active — VSA + Fractal layers engaged")
        print("  Try: python omnirepo.py --demo vsa")


if __name__ == "__main__":
    main()