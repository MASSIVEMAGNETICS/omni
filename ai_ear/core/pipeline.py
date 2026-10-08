#!/usr/bin/env python3
"""The AI Ear acoustic analysis pipeline.

This module is deliberately local and deterministic.  It does not pretend that
silence, ``None`` or an unavailable microphone is audio evidence.  Certification
paths must provide RIFF/WAVE integer PCM format-tag-1 bytes or a matching file.
WAVE_FORMAT_EXTENSIBLE is rejected consistently until a dedicated parser is
implemented, instead of inheriting Python-version-dependent behavior.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
import math
import os
from pathlib import Path
import stat
import struct
import tempfile
from typing import BinaryIO, Dict, Iterator, List, Optional, Tuple, Union
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
    MAX_DURATION_SECONDS = 10 * 60
    MAX_DECODED_SAMPLES = 30_000_000
    CHUNK_FRAMES = 8192
    FILE_COPY_CHUNK_BYTES = 1024 * 1024
    MAX_RIFF_CHUNKS = 1024

    def __init__(self, memory: Optional[SharedMemoryGraph] = None):
        self.memory = memory if memory is not None else SharedMemoryGraph()
        print("[The AI Ear] Initialized with deterministic local WAV analysis")

    @staticmethod
    def _file_version(file_stat: os.stat_result) -> Tuple[int, int, int, int, int]:
        """Return mutation-relevant metadata for an already-open file."""
        return (
            file_stat.st_dev,
            file_stat.st_ino,
            file_stat.st_size,
            file_stat.st_mtime_ns,
            file_stat.st_ctime_ns,
        )

    @classmethod
    @contextmanager
    def _snapshot_file(cls, path: Path) -> Iterator[Tuple[BinaryIO, str]]:
        """Open once and yield an immutable, hash-bound snapshot of ``path``.

        The pathname is never reopened for analysis. Small inputs remain in
        memory; larger bounded inputs spill to an anonymous temporary file.
        Metadata changes to the opened source during acquisition fail closed.
        """
        flags = os.O_RDONLY
        flags |= getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)

        try:
            descriptor = os.open(path, flags)
        except (OSError, TypeError) as exc:
            raise AudioAnalysisError(f"unable to open audio file: {exc}") from exc

        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise AudioAnalysisError("audio source must be a regular file")
            if before.st_size <= 0:
                raise AudioAnalysisError("audio file is empty")
            if before.st_size > cls.MAX_FILE_BYTES:
                raise AudioAnalysisError(
                    f"audio file exceeds {cls.MAX_FILE_BYTES} byte limit"
                )

            with os.fdopen(descriptor, "rb", closefd=True) as source_handle:
                descriptor = -1
                with tempfile.SpooledTemporaryFile(
                    max_size=cls.MAX_IN_MEMORY_BYTES,
                    mode="w+b",
                ) as snapshot:
                    digest = hashlib.sha256()
                    total_bytes = 0

                    while True:
                        try:
                            chunk = source_handle.read(cls.FILE_COPY_CHUNK_BYTES)
                        except OSError as exc:
                            raise AudioAnalysisError(
                                f"unable to snapshot audio file: {exc}"
                            ) from exc
                        if not chunk:
                            break
                        total_bytes += len(chunk)
                        if total_bytes > cls.MAX_FILE_BYTES:
                            raise AudioAnalysisError(
                                f"audio file exceeds {cls.MAX_FILE_BYTES} byte limit"
                            )
                        digest.update(chunk)
                        snapshot.write(chunk)

                    after = os.fstat(source_handle.fileno())
                    if cls._file_version(before) != cls._file_version(after):
                        raise AudioAnalysisError(
                            "audio file changed while evidence was being acquired"
                        )
                    if total_bytes == 0:
                        raise AudioAnalysisError("audio file is empty")

                    snapshot.seek(0)
                    yield snapshot, digest.hexdigest()
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    @classmethod
    def _require_supported_wave_format(cls, handle: BinaryIO) -> None:
        """Enforce one WAV contract on every supported Python runtime."""
        original_position = handle.tell()
        try:
            handle.seek(0, os.SEEK_END)
            total_size = handle.tell()
            handle.seek(0)
            header = handle.read(12)
            if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
                raise AudioAnalysisError("input is not a RIFF/WAVE container")

            riff_end = struct.unpack("<I", header[4:8])[0] + 8
            if riff_end < 12 or riff_end > total_size:
                raise AudioAnalysisError("RIFF/WAVE container is truncated")

            cursor = 12
            for _ in range(cls.MAX_RIFF_CHUNKS):
                if cursor + 8 > riff_end:
                    break
                handle.seek(cursor)
                chunk_header = handle.read(8)
                if len(chunk_header) != 8:
                    raise AudioAnalysisError("RIFF/WAVE chunk header is truncated")

                chunk_id = chunk_header[:4]
                chunk_size = struct.unpack("<I", chunk_header[4:])[0]
                chunk_data_start = cursor + 8
                chunk_data_end = chunk_data_start + chunk_size
                if chunk_data_end > riff_end or chunk_data_end > total_size:
                    raise AudioAnalysisError("RIFF/WAVE chunk data is truncated")

                if chunk_id == b"fmt ":
                    if chunk_size < 16:
                        raise AudioAnalysisError("RIFF/WAVE fmt chunk is too short")
                    handle.seek(chunk_data_start)
                    format_tag_bytes = handle.read(2)
                    if len(format_tag_bytes) != 2:
                        raise AudioAnalysisError("RIFF/WAVE fmt tag is truncated")
                    format_tag = struct.unpack("<H", format_tag_bytes)[0]
                    if format_tag == 1:
                        return
                    if format_tag == 0xFFFE:
                        raise AudioAnalysisError(
                            "WAVE_FORMAT_EXTENSIBLE is not supported; "
                            "use RIFF/WAVE integer PCM format tag 1"
                        )
                    raise AudioAnalysisError(
                        f"unsupported WAV format tag: {format_tag}"
                    )

                cursor = chunk_data_end + (chunk_size & 1)
            else:
                raise AudioAnalysisError("RIFF/WAVE contains too many chunks")

            raise AudioAnalysisError("RIFF/WAVE fmt chunk is missing")
        finally:
            handle.seek(original_position)

    @classmethod
    def _analyze_snapshot(
        cls,
        snapshot: BinaryIO,
        *,
        source_label: str,
    ) -> Dict[str, float]:
        snapshot.seek(0)
        cls._require_supported_wave_format(snapshot)
        snapshot.seek(0)
        try:
            with wave.open(snapshot, "rb") as handle:
                return cls._measure_wave(handle)
        except AudioAnalysisError:
            raise
        except (wave.Error, EOFError, OSError, struct.error) as exc:
            raise AudioAnalysisError(
                f"invalid format-tag-1 PCM WAV {source_label}: {exc}"
            ) from exc

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
        if sample_width not in (1, 2, 3, 4):
            raise AudioAnalysisError(
                f"unsupported PCM sample width: {sample_width} bytes"
            )
        if frame_count <= 0:
            raise AudioAnalysisError("audio contains no PCM frames")
        if frame_count > sample_rate * cls.MAX_DURATION_SECONDS:
            raise AudioAnalysisError(
                f"audio exceeds {cls.MAX_DURATION_SECONDS} second duration limit"
            )

        declared_samples = frame_count * channels
        if declared_samples > cls.MAX_DECODED_SAMPLES:
            raise AudioAnalysisError(
                f"audio exceeds {cls.MAX_DECODED_SAMPLES} decoded sample limit"
            )

        sum_sq = 0.0
        sum_value = 0.0
        peak = 0.0
        zero_crossings = 0
        mono_frames = 0
        decoded_samples = 0
        previous: Optional[float] = None
        bytes_per_frame = sample_width * channels

        while True:
            raw = handle.readframes(cls.CHUNK_FRAMES)
            if not raw:
                break
            if len(raw) % bytes_per_frame:
                raise AudioAnalysisError("PCM data ends with a partial frame")

            chunk_samples = len(raw) // sample_width
            if decoded_samples + chunk_samples > cls.MAX_DECODED_SAMPLES:
                raise AudioAnalysisError(
                    f"audio exceeds {cls.MAX_DECODED_SAMPLES} decoded sample limit"
                )

            samples = cls._decode_pcm(raw, sample_width)
            if len(samples) != chunk_samples:
                raise AudioAnalysisError("PCM decoder returned an incomplete chunk")

            chunk_frames = chunk_samples // channels
            if mono_frames + chunk_frames > frame_count:
                raise AudioAnalysisError("decoded frame count exceeds WAV header")

            decoded_samples += chunk_samples
            for index in range(0, len(samples), channels):
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
        if mono_frames != frame_count:
            raise AudioAnalysisError(
                f"PCM data is truncated: expected {frame_count} frames, "
                f"decoded {mono_frames}"
            )

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
            with io.BytesIO(payload) as snapshot:
                features = cls._analyze_snapshot(
                    snapshot,
                    source_label="payload",
                )
            source_kind = "bytes"
        else:
            try:
                path = Path(source).expanduser()
            except (TypeError, ValueError) as exc:
                raise AudioAnalysisError(f"invalid audio path: {exc}") from exc

            with cls._snapshot_file(path) as (snapshot, sha256):
                features = cls._analyze_snapshot(
                    snapshot,
                    source_label="file",
                )
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
