#!/usr/bin/env python3
"""The AI Ear acoustic analysis pipeline.

This module is deliberately local and deterministic.  It does not pretend that
silence, ``None`` or an unavailable microphone is audio evidence.  Certification
paths must provide real PCM WAV bytes or a real WAV file path.
"""

from __future__ import annotations

import hashlib
import io
import math
import os
from pathlib import Path
import struct
from typing import BinaryIO, Dict, Iterable, List, Optional, Union
import wave

from core.memory_graph import SharedMemoryGraph

AudioSource = Union[str, os.PathLike, bytes, bytearray]


class AudioAnalysisError(ValueError):
    """Raised when input cannot be treated as bounded PCM WAV evidence."""


class AudioPipeline:
    """Deterministic, offline acoustic feature extractor.

    The first objective is evidentiary integrity, not pretending to be a full
    learned auditory model.  Every result is tied to the SHA-256 of the exact
    input bytes and contains signal-derived measurements.
    """

    MAX_IN_MEMORY_BYTES = 64 * 1024 * 1024
    MAX_FILE_BYTES = 512 * 1024 * 1024
    CHUNK_FRAMES = 8192

    def __init__(self, memory: Optional[SharedMemoryGraph] = None):
        self.memory = memory if memory is not None else SharedMemoryGraph()
        print("[The AI Ear] Initialized with deterministic local WAV analysis")

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _decode_pcm(raw: bytes, sample_width: int) -> List[float]:
        """Decode little-endian integer PCM into floats in approximately [-1, 1]."""
        if sample_width == 1:
            return [(value - 128) / 128.0 for value in raw]
        if sample_width == 2:
            count = len(raw) // 2
            return [value / 32768.0 for value in struct.unpack(f"<{count}h", raw)]
        if sample_width == 3:
            output: List[float] = []
            for offset in range(0, len(raw), 3):
                triple = raw[offset : offset + 3]
                if len(triple) != 3:
                    break
                value = int.from_bytes(triple, byteorder="little", signed=False)
                if value & 0x800000:
                    value -= 1 << 24
                output.append(value / 8388608.0)
            return output
        if sample_width == 4:
            count = len(raw) // 4
            return [value / 2147483648.0 for value in struct.unpack(f"<{count}i", raw)]
        raise AudioAnalysisError(f"unsupported PCM sample width: {sample_width} bytes")

    @classmethod
    def _measure_wave(cls, handle: wave.Wave_read) -> Dict[str, float]:
        if handle.getcomptype() != "NONE":
            raise AudioAnalysisError("only uncompressed PCM WAV is accepted")

        channels = handle.getnchannels()
        sample_rate = handle.getframerate()
        sample_width = handle.getsampwidth()
        frame_count = handle.getnframes()

        if channels < 1 or channels > 32:
            raise AudioAnalysisError(f"invalid channel count: {channels}")
        if sample_rate <= 0 or sample_rate > 768000:
            raise AudioAnalysisError(f"invalid sample rate: {sample_rate}")
        if frame_count <= 0:
            raise AudioAnalysisError("audio contains no PCM frames")

        sum_sq = 0.0
        sum_value = 0.0
        peak = 0.0
        zero_crossings = 0
        mono_frames = 0
        previous: Optional[float] = None

        while True:
            raw = handle.readframes(cls.CHUNK_FRAMES)
            if not raw:
                break
            samples = cls._decode_pcm(raw, sample_width)
            usable = len(samples) - (len(samples) % channels)
            for index in range(0, usable, channels):
                frame = samples[index : index + channels]
                mono = sum(frame) / channels
                absolute = abs(mono)
                peak = max(peak, absolute)
                sum_sq += mono * mono
                sum_value += mono
                if previous is not None and ((previous < 0.0 <= mono) or (previous >= 0.0 > mono)):
                    zero_crossings += 1
                previous = mono
                mono_frames += 1

        if mono_frames == 0:
            raise AudioAnalysisError("audio decoded to zero frames")

        rms = math.sqrt(sum_sq / mono_frames)
        duration = mono_frames / float(sample_rate)
        zcr = zero_crossings / max(1, mono_frames - 1)
        dc_offset = sum_value / mono_frames
        crest_factor = peak / rms if rms > 0.0 else 0.0

        return {
            "sample_rate_hz": int(sample_rate),
            "channels": int(channels),
            "sample_width_bits": int(sample_width * 8),
            "frame_count": int(mono_frames),
            "duration_seconds": round(duration, 9),
            "rms": round(rms, 12),
            "peak": round(peak, 12),
            "zero_crossing_rate": round(zcr, 12),
            "dc_offset": round(dc_offset, 12),
            "crest_factor": round(crest_factor, 12),
        }

    @classmethod
    def _analyze_source(cls, source: AudioSource) -> Dict[str, object]:
        if source is None:  # type: ignore[comparison-overlap]
            raise AudioAnalysisError("real audio evidence is required; None is not audio")

        if isinstance(source, (bytes, bytearray)):
            payload = bytes(source)
            if not payload:
                raise AudioAnalysisError("audio payload is empty")
            if len(payload) > cls.MAX_IN_MEMORY_BYTES:
                raise AudioAnalysisError(
                    f"in-memory audio exceeds {cls.MAX_IN_MEMORY_BYTES} byte limit"
                )
            sha256 = hashlib.sha256(payload).hexdigest()
            try:
                with wave.open(io.BytesIO(payload), "rb") as handle:
                    features = cls._measure_wave(handle)
            except (wave.Error, EOFError) as exc:
                raise AudioAnalysisError(f"invalid PCM WAV payload: {exc}") from exc
            source_kind = "bytes"
        else:
            path = Path(source).expanduser().resolve(strict=True)
            stat = path.stat()
            if not path.is_file():
                raise AudioAnalysisError("audio source must be a regular file")
            if stat.st_size <= 0:
                raise AudioAnalysisError("audio file is empty")
            if stat.st_size > cls.MAX_FILE_BYTES:
                raise AudioAnalysisError(
                    f"audio file exceeds {cls.MAX_FILE_BYTES} byte limit"
                )
            sha256 = cls._hash_file(path)
            try:
                with wave.open(str(path), "rb") as handle:
                    features = cls._measure_wave(handle)
            except (wave.Error, EOFError) as exc:
                raise AudioAnalysisError(f"invalid PCM WAV file: {exc}") from exc
            source_kind = "file"

        return {
            "schema": "omni.ai_ear.acoustic_frame.v1",
            "source_kind": source_kind,
            "sha256": sha256,
            "features": features,
        }

    def process_audio(self, audio_data: AudioSource) -> Dict[str, object]:
        result = self._analyze_source(audio_data)
        result["evidence"] = {
            "input_is_real": True,
            "deterministic": True,
            "network_required": False,
            "raw_audio_persisted": False,
        }
        self.memory.add_event(result, source="ai_ear", importance=0.7)
        return result

    def listen(self, duration: int = 30, audio_source: Optional[AudioSource] = None) -> Dict[str, object]:
        """Analyze explicitly supplied evidence; fail closed if capture is unavailable.

        Live microphone capture is intentionally not fabricated.  A future local
        capture adapter may supply real WAV evidence here under its own permission
        and provenance boundary.
        """
        if duration <= 0:
            raise ValueError("duration must be positive")
        if audio_source is None:
            raise AudioAnalysisError(
                "no local capture adapter is installed; provide real WAV evidence via audio_source"
            )
        return self.process_audio(audio_source)
