from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Callable

ProbeRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class ModelProbe:
    def __init__(
        self,
        cache_path: str | Path | None = None,
        ttl_seconds: int = 3600,
        runner: ProbeRunner | None = None,
    ) -> None:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be >= 0")
        self.cache_path = (
            Path(cache_path)
            if cache_path
            else Path.home() / ".cache" / "bookweaver" / "model_probe_cache.json"
        )
        self.ttl_seconds = ttl_seconds
        self.runner = runner or self._default_runner
        self.last_probe_errors: dict[str, str] = {}
        self.last_cache_warning: str | None = None

    def _default_runner(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )

    def load_cache(self) -> dict[str, object]:
        if not self.cache_path.exists():
            return {}
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload

    def save_cache(self, payload: dict[str, object]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _is_cache_fresh(self, payload: dict[str, object]) -> bool:
        timestamp = payload.get("timestamp")
        if not isinstance(timestamp, (int, float)):
            return False
        return (time.time() - float(timestamp)) <= self.ttl_seconds

    def probe(self, candidates: list[str]) -> dict[str, bool]:
        if not candidates:
            raise ValueError("candidates must not be empty")

        payload = self.load_cache()
        cache_fresh = self._is_cache_fresh(payload)
        cached_results_raw = payload.get("results")
        cached_errors_raw = payload.get("errors")
        cached_results: dict[str, bool] = {}
        if isinstance(cached_results_raw, dict):
            cached_results = {
                str(key): value
                for key, value in cached_results_raw.items()
                if isinstance(value, bool)
            }
        cached_errors: dict[str, str] = {}
        if isinstance(cached_errors_raw, dict):
            cached_errors = {
                str(key): value
                for key, value in cached_errors_raw.items()
                if isinstance(value, str)
            }

        results: dict[str, bool] = {}
        errors: dict[str, str] = {}
        probed_any = False

        for candidate in candidates:
            if cache_fresh and candidate in cached_results:
                is_available = cached_results[candidate]
                results[candidate] = is_available
                if not is_available and candidate in cached_errors:
                    errors[candidate] = cached_errors[candidate]
                continue

            try:
                completed = self.runner(["gemini", "--model", candidate, "-p", "ping"])
                is_available = completed.returncode == 0
                results[candidate] = is_available
                if not is_available:
                    stderr = (completed.stderr or "").strip()
                    errors[candidate] = stderr[:200] if stderr else "unknown probe failure"
            except Exception as exc:
                results[candidate] = False
                errors[candidate] = str(exc)[:200] if str(exc) else "probe runner exception"
            probed_any = True

        self.last_probe_errors = errors

        if probed_any:
            merged_results = dict(cached_results)
            merged_results.update(results)
            merged_errors = dict(cached_errors)
            merged_errors.update(errors)
            for model_name, is_available in results.items():
                if is_available and model_name in merged_errors:
                    del merged_errors[model_name]

            payload = {
                "timestamp": time.time(),
                "results": merged_results,
                "errors": merged_errors,
            }
            try:
                self.save_cache(payload)
                self.last_cache_warning = None
            except OSError as exc:
                self.last_cache_warning = str(exc)

        return results
