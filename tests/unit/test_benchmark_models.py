from __future__ import annotations

from pathlib import Path

from benchmark_models import sample_chunk_files


def test_sample_chunk_files_selects_head_middle_tail(temp_dir: Path):
    for index in range(1, 8):
        p = temp_dir / f"page{index:04d}.md"
        p.write_text(f"chunk-{index}", encoding="utf-8")

    selected = sample_chunk_files(temp_dir=temp_dir, sample_count=3)
    names = [p.name for p in selected]
    assert names == ["page0001.md", "page0004.md", "page0007.md"]
