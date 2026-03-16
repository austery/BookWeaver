from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    project_root = Path(__file__).resolve().parents[2]
    file_path = project_root / "05_md_to_html.py"
    spec = importlib.util.spec_from_file_location("step5_module", file_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load 05_md_to_html.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_render_alternating_bilingual_html_contains_both_languages():
    module = _load_module()
    md = """## Segment 1

Hello world.

**中文译文**

你好，世界。

---
"""
    html = module.render_alternating_bilingual_html(md)
    assert "Hello world." in html
    assert "你好，世界。" in html
    assert "class=\"source-text\"" in html
    assert "class=\"translated-text\"" in html

