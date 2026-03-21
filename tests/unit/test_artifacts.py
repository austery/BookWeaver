from __future__ import annotations

import json
from pathlib import Path

from ai.artifacts import OrchestrationArtifacts


def test_artifacts_write_paths_and_metrics(tmp_path: Path) -> None:
    artifacts = OrchestrationArtifacts(temp_dir=tmp_path)
    analysis = artifacts.analysis_path()
    prompt = artifacts.prompt_path()
    metrics = artifacts.metrics_path()

    artifacts.write_text(analysis, "analysis")
    artifacts.write_text(prompt, "prompt")
    artifacts.write_metrics({"runtime_ratio": 1.8, "quality_delta": 5.2})

    assert analysis.exists()
    assert prompt.exists()
    assert metrics.exists()
    payload = json.loads(metrics.read_text(encoding="utf-8"))
    assert payload["runtime_ratio"] == 1.8
