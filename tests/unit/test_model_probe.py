from __future__ import annotations

import json
import time
from pathlib import Path
from subprocess import CompletedProcess

from ai.model_probe import ModelProbe


def test_probe_uses_cache_when_fresh(tmp_path: Path):
    cache_path = tmp_path / "model_probe_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "timestamp": time.time(),
                "results": {"gemini-2.5-pro": True},
                "errors": {},
            }
        ),
        encoding="utf-8",
    )
    called = {"count": 0}

    def fake_runner(_: list[str]) -> CompletedProcess[str]:
        called["count"] += 1
        return CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")

    probe = ModelProbe(cache_path=cache_path, ttl_seconds=3600, runner=fake_runner)
    results = probe.probe(["gemini-2.5-pro"])
    assert results["gemini-2.5-pro"] is True
    assert called["count"] == 0


def test_probe_marks_unavailable_model(tmp_path: Path):
    cache_path = tmp_path / "model_probe_cache.json"

    def fake_runner(_: list[str]) -> CompletedProcess[str]:
        return CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="model not found: gemini-9",
        )

    probe = ModelProbe(cache_path=cache_path, ttl_seconds=0, runner=fake_runner)
    results = probe.probe(["gemini-9"])
    assert results["gemini-9"] is False
    assert "model not found" in probe.last_probe_errors["gemini-9"]


def test_probe_continues_when_runner_raises(tmp_path: Path):
    cache_path = tmp_path / "model_probe_cache.json"
    calls = {"count": 0}

    def fake_runner(command: list[str]) -> CompletedProcess[str]:
        calls["count"] += 1
        model = command[2]
        if model == "gemini-bad":
            raise RuntimeError("probe timeout")
        return CompletedProcess(args=command, returncode=0, stdout="ok", stderr="")

    probe = ModelProbe(cache_path=cache_path, ttl_seconds=0, runner=fake_runner)
    results = probe.probe(["gemini-bad", "gemini-good"])
    assert calls["count"] == 2
    assert results == {"gemini-bad": False, "gemini-good": True}
    assert "probe timeout" in probe.last_probe_errors["gemini-bad"]


def test_probe_ignores_corrupt_cache_and_probes(tmp_path: Path):
    cache_path = tmp_path / "model_probe_cache.json"
    cache_path.write_text("{broken-json", encoding="utf-8")

    def fake_runner(command: list[str]) -> CompletedProcess[str]:
        return CompletedProcess(args=command, returncode=0, stdout="ok", stderr="")

    probe = ModelProbe(cache_path=cache_path, ttl_seconds=3600, runner=fake_runner)
    results = probe.probe(["gemini-2.5-pro"])
    assert results["gemini-2.5-pro"] is True


def test_probe_ignores_cache_write_error(tmp_path: Path):
    cache_path = tmp_path / "model_probe_cache.json"

    def fake_runner(command: list[str]) -> CompletedProcess[str]:
        return CompletedProcess(args=command, returncode=0, stdout="ok", stderr="")

    probe = ModelProbe(cache_path=cache_path, ttl_seconds=0, runner=fake_runner)
    probe.save_cache = lambda _: (_ for _ in ()).throw(OSError("permission denied"))
    results = probe.probe(["gemini-2.5-pro"])
    assert results["gemini-2.5-pro"] is True
    assert probe.last_cache_warning is not None
    assert "permission denied" in probe.last_cache_warning
