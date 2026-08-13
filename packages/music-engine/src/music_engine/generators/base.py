"""Stable contract between sovereign orchestration and disposable generators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


class AdapterError(RuntimeError):
    """Base class for generator adapter failures."""


class AdapterUnavailableError(AdapterError):
    """Raised when the configured generator service cannot be reached."""


@dataclass(frozen=True)
class GenerationCandidate:
    audio_path: Path
    seed: int
    adapter_id: str
    adapter_revision: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class GeneratorAdapter(ABC):
    """Minimal model-independent generation contract."""

    adapter_id: str
    adapter_revision: str | None = None

    @property
    @abstractmethod
    def capabilities(self) -> frozenset[str]:
        raise NotImplementedError

    @abstractmethod
    def generate_batch(
        self,
        song_plan: Mapping[str, Any],
        count: int = 4,
        seed: int = 42,
    ) -> list[GenerationCandidate]:
        """Generate N candidate files from one canonical SongPlan."""
        raise NotImplementedError

    @abstractmethod
    def repaint(
        self,
        audio_path: Path,
        mask_start_sec: float,
        mask_end_sec: float,
        prompt: str,
        *,
        seed: int = 42,
    ) -> GenerationCandidate:
        """Repaint one bounded region without changing the caller contract."""
        raise NotImplementedError
