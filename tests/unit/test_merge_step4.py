from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    project_root = Path(__file__).resolve().parents[2]
    file_path = project_root / "04_merge_md.py"
    spec = importlib.util.spec_from_file_location("step4_module", file_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load 04_merge_md.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_merge_step4_produces_bilingual_output(temp_dir: Path):
    module = _load_module()
    (temp_dir / "page0001.md").write_text("Hello.", encoding="utf-8")
    (temp_dir / "output_page0001.md").write_text("你好。", encoding="utf-8")
    out = module.merge_markdown_files(temp_dir=temp_dir)
    content = out.read_text(encoding="utf-8")
    assert "Hello." in content
    assert "你好。" in content
    assert "**中文译文**" in content

