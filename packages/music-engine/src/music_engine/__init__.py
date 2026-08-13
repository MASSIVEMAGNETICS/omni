"""Sovereign model-agnostic music generation runtime."""

from .pipeline.closed_loop import ClosedLoopResult, ClosedLoopRunner

__all__ = ["ClosedLoopResult", "ClosedLoopRunner"]
