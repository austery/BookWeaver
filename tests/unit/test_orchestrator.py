from __future__ import annotations

from pathlib import Path

from ai.orchestrator import run_orchestrated_translation


def test_orchestrator_writes_required_artifacts(tmp_path: Path) -> None:
    pages = {"page0001.md": "Source paragraph."}
    result = run_orchestrated_translation(
        temp_dir=tmp_path,
        pages=pages,
        output_lang="zh",
    )
    assert (tmp_path / "orchestration" / "01-analysis.md").exists()
    assert (tmp_path / "orchestration" / "02-prompt.md").exists()
    assert (tmp_path / "orchestration" / "04-critique.md").exists()
    assert (tmp_path / "orchestration" / "05-revision.md").exists()
    assert (tmp_path / "orchestration" / "06-polish.md").exists()
    assert "page0001.md" in result
