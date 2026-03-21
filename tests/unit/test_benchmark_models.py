from __future__ import annotations

from pathlib import Path

from benchmark_models import build_mode_gate_report, sample_chunk_files


def test_sample_chunk_files_selects_head_middle_tail(temp_dir: Path):
    for index in range(1, 8):
        p = temp_dir / f"page{index:04d}.md"
        p.write_text(f"chunk-{index}", encoding="utf-8")

    selected = sample_chunk_files(temp_dir=temp_dir, sample_count=3)
    names = [p.name for p in selected]
    assert names == ["page0001.md", "page0004.md", "page0007.md"]


def test_build_mode_gate_report_includes_quality_runtime_and_decision() -> None:
    report = build_mode_gate_report(
        fast_scores={"terminology": 70, "fidelity": 72, "fluency": 74},
        orchestrated_scores={"terminology": 78, "fidelity": 80, "fluency": 82},
        fast_runtime_seconds=100.0,
        orchestrated_runtime_seconds=180.0,
    )

    assert "quality_delta" in report
    assert "runtime_ratio" in report
    assert "gate_decision" in report
    assert report["gate_decision"] == "adopt"
