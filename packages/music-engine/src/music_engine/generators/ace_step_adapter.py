"""ACE-Step 1.5 adapter using the project's verified local FastAPI contract."""

from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from .base import AdapterError, AdapterUnavailableError, GenerationCandidate, GeneratorAdapter


class AceStepAdapter(GeneratorAdapter):
    adapter_id = "ace-step-1.5"
    adapter_revision = "api-v1"

    def __init__(self, base_url: str = "http://127.0.0.1:8001", *, output_dir: Path | str = Path("artifacts/ace-step"), api_key: str | None = None, timeout_s: float = 3600.0, poll_interval_s: float = 1.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.output_dir = Path(output_dir)
        self.api_key = api_key
        self.timeout_s = float(timeout_s)
        self.poll_interval_s = float(poll_interval_s)
        if self.timeout_s <= 0 or self.poll_interval_s <= 0:
            raise ValueError("timeout_s and poll_interval_s must be positive")

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"generate", "repaint", "cover", "wav"})

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request_json(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(f"{self.base_url}{path}", data=body, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(request, timeout=min(self.timeout_s, 60.0)) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise AdapterUnavailableError(f"ACE-Step API unavailable at {self.base_url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise AdapterError("ACE-Step API returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise AdapterError("ACE-Step API returned an unexpected response shape")
        code = decoded.get("code", 200)
        if code not in (0, 200, None):
            raise AdapterError(f"ACE-Step API error {code}: {decoded.get('error')}")
        return decoded

    @staticmethod
    def _production_style(song_plan: Mapping[str, Any]) -> str:
        production = song_plan.get("production", {})
        if isinstance(production, Mapping):
            return str(production.get("style") or production.get("description") or song_plan.get("style") or "")
        return str(song_plan.get("style") or "")

    @staticmethod
    def _song_lyrics(song_plan: Mapping[str, Any]) -> str:
        lyrics = song_plan.get("lyrics", "")
        if isinstance(lyrics, str):
            return lyrics
        if isinstance(lyrics, Mapping):
            for key in ("text", "raw", "content"):
                if key in lyrics:
                    return str(lyrics[key])
        return str(lyrics or "")

    def _build_generate_payload(self, song_plan: Mapping[str, Any], *, seed: int, src_audio_path: str | None = None, task_type: str = "text2music", repaint_start: float = 0.0, repaint_end: float | None = None, repaint_prompt: str | None = None) -> dict[str, Any]:
        style = repaint_prompt if repaint_prompt is not None else self._production_style(song_plan)
        duration = song_plan.get("duration", song_plan.get("duration_target"))
        bpm = song_plan.get("bpm")
        key = song_plan.get("key", song_plan.get("key_scale", ""))
        meter = song_plan.get("time_signature", song_plan.get("meter", ""))
        payload: dict[str, Any] = {
            "prompt": str(style),
            "lyrics": self._song_lyrics(song_plan),
            "thinking": bool(song_plan.get("thinking", False)),
            "bpm": int(round(float(bpm))) if bpm is not None else None,
            "key_scale": str(key or ""),
            "time_signature": str(meter or ""),
            "audio_duration": float(duration) if duration is not None else None,
            "batch_size": 1,
            "use_random_seed": False,
            "seed": int(seed),
            "audio_format": "wav",
            "task_type": task_type,
        }
        if src_audio_path is not None:
            payload["src_audio_path"] = src_audio_path
        if repaint_end is not None:
            payload["repainting_start"] = float(repaint_start)
            payload["repainting_end"] = float(repaint_end)
        return payload

    def _submit(self, payload: Mapping[str, Any]) -> str:
        response = self._request_json("/release_task", payload)
        data = response.get("data")
        if not isinstance(data, Mapping) or not data.get("task_id"):
            raise AdapterError(f"ACE-Step task submission lacked task_id: {response!r}")
        return str(data["task_id"])

    def _wait_for_tasks(self, task_ids: list[str]) -> dict[str, dict[str, Any]]:
        deadline = time.monotonic() + self.timeout_s
        pending = set(task_ids)
        completed: dict[str, dict[str, Any]] = {}
        while pending:
            if time.monotonic() >= deadline:
                raise AdapterError(f"Timed out waiting for ACE-Step tasks: {sorted(pending)}")
            response = self._request_json("/query_result", {"task_id_list": list(pending)})
            rows = response.get("data")
            if not isinstance(rows, list):
                raise AdapterError(f"Unexpected ACE-Step result payload: {response!r}")
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                task_id = str(row.get("task_id", ""))
                if task_id not in pending:
                    continue
                status = int(row.get("status", 0))
                if status == 2:
                    raise AdapterError(f"ACE-Step task {task_id} failed: {row.get('result', '[]')}")
                if status == 1:
                    completed[task_id] = dict(row)
                    pending.remove(task_id)
            if pending:
                time.sleep(self.poll_interval_s)
        return completed

    def _decode_result_item(self, row: Mapping[str, Any]) -> Mapping[str, Any]:
        raw = row.get("result", "[]")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise AdapterError("ACE-Step result field was not valid JSON") from exc
        else:
            parsed = raw
        if not isinstance(parsed, list) or not parsed or not isinstance(parsed[0], Mapping):
            raise AdapterError(f"ACE-Step result contained no audio item: {parsed!r}")
        return parsed[0]

    def _materialize_audio(self, source: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        local_source = Path(source)
        if source and local_source.exists():
            shutil.copy2(local_source, destination)
            return
        if source.startswith("http://") or source.startswith("https://"):
            url = source
        elif source.startswith("/v1/audio"):
            url = f"{self.base_url}{source}"
        else:
            url = f"{self.base_url}/v1/audio?{urllib.parse.urlencode({'path': source})}"
        request = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=min(self.timeout_s, 120.0)) as response:
                with destination.open("wb") as handle:
                    shutil.copyfileobj(response, handle)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise AdapterError(f"Could not download ACE-Step audio from {url}: {exc}") from exc
        if not destination.exists() or destination.stat().st_size == 0:
            raise AdapterError(f"ACE-Step produced an empty audio file: {destination}")

    def generate_batch(self, song_plan: Mapping[str, Any], count: int = 4, seed: int = 42) -> list[GenerationCandidate]:
        if count < 1:
            raise ValueError("count must be >= 1")
        task_to_seed: dict[str, int] = {}
        for index in range(count):
            candidate_seed = int(seed) + index
            task_id = self._submit(self._build_generate_payload(song_plan, seed=candidate_seed))
            task_to_seed[task_id] = candidate_seed
        completed = self._wait_for_tasks(list(task_to_seed))
        candidates: list[GenerationCandidate] = []
        for task_id, candidate_seed in task_to_seed.items():
            item = self._decode_result_item(completed[task_id])
            source = str(item.get("file") or "")
            if not source:
                raise AdapterError(f"ACE-Step task {task_id} succeeded without an audio path")
            output_path = self.output_dir / f"candidate_{candidate_seed}.wav"
            self._materialize_audio(source, output_path)
            candidates.append(GenerationCandidate(audio_path=output_path, seed=candidate_seed, adapter_id=self.adapter_id, adapter_revision=self.adapter_revision, metadata={"task_id": task_id, "ace_metas": dict(item.get("metas") or {})}))
        return candidates

    def repaint(self, audio_path: Path, mask_start_sec: float, mask_end_sec: float, prompt: str, *, seed: int = 42) -> GenerationCandidate:
        if not audio_path.exists():
            raise FileNotFoundError(audio_path)
        if mask_start_sec < 0 or mask_end_sec <= mask_start_sec:
            raise ValueError("repaint bounds must satisfy 0 <= start < end")
        song_plan: dict[str, Any] = {"production": {"style": prompt}, "lyrics": ""}
        task_id = self._submit(self._build_generate_payload(song_plan, seed=seed, src_audio_path=str(audio_path.resolve()), task_type="repaint", repaint_start=mask_start_sec, repaint_end=mask_end_sec, repaint_prompt=prompt))
        row = self._wait_for_tasks([task_id])[task_id]
        item = self._decode_result_item(row)
        source = str(item.get("file") or "")
        if not source:
            raise AdapterError(f"ACE-Step repaint task {task_id} returned no audio path")
        output_path = self.output_dir / f"{audio_path.stem}_repaint_{seed}.wav"
        self._materialize_audio(source, output_path)
        return GenerationCandidate(audio_path=output_path, seed=seed, adapter_id=self.adapter_id, adapter_revision=self.adapter_revision, metadata={"task_id": task_id, "operation": "repaint"})
