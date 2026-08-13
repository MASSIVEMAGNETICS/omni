"""Translate AI Ear `/analyse` output into BandoRank metrics."""

from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Any, Mapping

from audio_ear.scoring.bandorank import EarMetrics


class EvaluationError(RuntimeError):
    """Raised when a candidate cannot be evaluated reliably."""


_ENHARMONIC = {"db": "c#", "eb": "d#", "gb": "f#", "ab": "g#", "bb": "a#"}


def _normalize_key(value: str) -> tuple[str, str]:
    text = str(value or "").strip().lower().replace("♭", "b").replace("♯", "#")
    compact = re.sub(r"\s+", "", text)
    mode = ""
    if compact.endswith("minor"):
        mode, compact = "minor", compact[:-5]
    elif compact.endswith("major"):
        mode, compact = "major", compact[:-5]
    elif compact.endswith("min"):
        mode, compact = "minor", compact[:-3]
    elif compact.endswith("maj"):
        mode, compact = "major", compact[:-3]
    elif compact.endswith("m") and len(compact) > 1:
        mode, compact = "minor", compact[:-1]
    return _ENHARMONIC.get(compact, compact), mode


def key_match_score(target: str, detected: str) -> float:
    target_tonic, target_mode = _normalize_key(target)
    detected_tonic, detected_mode = _normalize_key(detected)
    if not target_tonic or not detected_tonic:
        return 0.0
    if target_tonic != detected_tonic:
        return 0.0
    if target_mode and detected_mode and target_mode != detected_mode:
        return 0.65
    return 1.0


def _normalize_lyric_tokens(text: str) -> list[str]:
    text = re.sub(r"\[[^\]]+\]", " ", text)
    return re.findall(r"[a-z0-9']+", text.lower())


def _token_accuracy(reference: str, hypothesis: str) -> float:
    ref = _normalize_lyric_tokens(reference)
    hyp = _normalize_lyric_tokens(hypothesis)
    if not ref:
        return 1.0
    previous = list(range(len(hyp) + 1))
    for i, ref_token in enumerate(ref, 1):
        current = [i]
        for j, hyp_token in enumerate(hyp, 1):
            current.append(min(previous[j - 1] + (ref_token != hyp_token), current[j - 1] + 1, previous[j] + 1))
        previous = current
    return max(0.0, 1.0 - (previous[-1] / len(ref)))


def _extract_plan_lyrics(song_plan: Mapping[str, Any]) -> str:
    lyrics = song_plan.get("lyrics", "")
    if isinstance(lyrics, str):
        return lyrics
    if isinstance(lyrics, Mapping):
        for key in ("text", "raw", "content"):
            if key in lyrics:
                return str(lyrics[key])
    return str(lyrics or "")


def _target_energy(song_plan: Mapping[str, Any]) -> float:
    production = song_plan.get("production", {})
    if isinstance(production, Mapping):
        for key in ("energy", "energy_target"):
            if key in production:
                return max(0.0, min(1.0, float(production[key])))
    if "energy" in song_plan:
        return max(0.0, min(1.0, float(song_plan["energy"])))
    return 0.5


def _pcm_clipping_ratio(path: Path) -> float:
    """Return fraction of near-full-scale PCM samples. Fails closed on unsupported WAV."""
    try:
        with wave.open(str(path), "rb") as wav:
            width = wav.getsampwidth()
            channels = wav.getnchannels()
            if width not in (1, 2, 3, 4) or channels < 1:
                raise EvaluationError(f"Unsupported WAV format: width={width}, channels={channels}")
            total = 0
            clipped = 0
            while True:
                frames = wav.readframes(65536)
                if not frames:
                    break
                if width == 1:
                    samples = (byte - 128 for byte in frames)
                    limit = 127
                else:
                    limit = (1 << (8 * width - 1)) - 1
                    def decode_samples():
                        for offset in range(0, len(frames) - width + 1, width):
                            raw = frames[offset : offset + width]
                            if width == 3:
                                raw += b"\xff" if raw[-1] & 0x80 else b"\x00"
                            yield int.from_bytes(raw, "little", signed=True)
                    samples = decode_samples()
                threshold = 0.995 * limit
                for sample in samples:
                    total += 1
                    if abs(sample) >= threshold:
                        clipped += 1
            if total == 0:
                raise EvaluationError(f"WAV contained no PCM samples: {path}")
            return clipped / total
    except (wave.Error, EOFError) as exc:
        raise EvaluationError(f"Cannot inspect WAV signal integrity for {path}: {exc}") from exc


def _multipart_body(path: Path) -> tuple[bytes, str]:
    boundary = f"----BandoEar{uuid.uuid4().hex}"
    head = (f"--{boundary}\r\n" f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n' "Content-Type: audio/wav\r\n\r\n").encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return head + path.read_bytes() + tail, boundary


class AiEarEvaluator:
    """HTTP evaluator for the canonical AI Ear service."""

    def __init__(self, base_url: str = "http://127.0.0.1:8080", *, timeout_s: float = 180.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = float(timeout_s)
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be positive")

    def _analyse(self, audio_path: Path) -> Mapping[str, Any]:
        body, boundary = _multipart_body(audio_path)
        request = urllib.request.Request(f"{self.base_url}/analyse", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise EvaluationError(f"AI Ear unavailable at {self.base_url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise EvaluationError("AI Ear returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise EvaluationError("AI Ear returned an unexpected response shape")
        return payload

    def evaluate(self, audio_path: Path, song_plan: Mapping[str, Any]) -> EarMetrics:
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            raise EvaluationError(f"Candidate audio missing or empty: {audio_path}")
        analysis = self._analyse(audio_path)
        music = analysis.get("music") or {}
        speech = analysis.get("speech") or {}
        environment = analysis.get("environment") or {}
        if not isinstance(music, Mapping): music = {}
        if not isinstance(speech, Mapping): speech = {}
        if not isinstance(environment, Mapping): environment = {}
        target_bpm = float(song_plan.get("bpm") or 0.0)
        detected_raw = music.get("tempo_bpm")
        if target_bpm <= 0 or detected_raw is None or float(detected_raw) <= 0:
            raise EvaluationError(f"Cannot compute tempo score: target={target_bpm!r}, detected={detected_raw!r}")
        detected_bpm = float(detected_raw)
        target_key = str(song_plan.get("key", song_plan.get("key_scale", "")) or "")
        key_score = key_match_score(target_key, str(music.get("key") or ""))
        detected_energy = max(0.0, min(1.0, float(music.get("energy") or 0.0)))
        energy_score = max(0.0, 1.0 - abs(_target_energy(song_plan) - detected_energy))
        lyrics = _extract_plan_lyrics(song_plan)
        lyric_alignment = _token_accuracy(lyrics, str(speech.get("text") or "")) if lyrics.strip() else 1.0
        clipping_ratio = _pcm_clipping_ratio(audio_path)
        artifact_score = max(0.0, min(1.0, clipping_ratio * 20.0))
        snr_db = float(environment.get("snr_db") or 0.0)
        if not math.isfinite(snr_db): snr_db = 0.0
        snr_score = max(0.0, min(1.0, (snr_db + 5.0) / 45.0))
        fidelity_score = max(0.0, min(1.0, (0.70 * snr_score) + (0.30 * (1.0 - artifact_score))))
        return EarMetrics(target_bpm=target_bpm, detected_bpm=detected_bpm, key_score=key_score, energy_score=energy_score, fidelity_score=fidelity_score, lyric_alignment_score=lyric_alignment, artifact_score=artifact_score)
