from __future__ import annotations

import importlib.util
import sys
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
    assert 'class="source-text"' in html
    assert 'class="translated-text"' in html


def test_step5_parse_args_accepts_bilingual_style(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "05_md_to_html.py",
            "--temp-dir",
            "/tmp/demo",
            "--bilingual-style",
            "alternating",
        ],
    )
    args = module.parse_args()
    assert args.bilingual_style == "alternating"


def test_parse_alternating_segments_missing_marker():
    """Test that parse_alternating_segments handles missing translation marker gracefully."""
    module = _load_module()
    # Input without the "**中文译文**" marker
    markdown = "## Segment 1\nSome English text\n---\n"
    result = module.parse_alternating_segments(markdown)
    # Should return some result (empty or with defaults)
    assert result is not None


def test_paragraphs_html_escapes_html_chars():
    """Test that HTML special characters are properly escaped to prevent XSS."""
    module = _load_module()
    # Input with HTML special characters
    text = "<script>alert('xss')</script> & \"quotes\""
    result = module._paragraphs_html(text, css_class="source-text")
    # Should escape the HTML or contain safe output
    assert "<script>" not in result
    assert "script" in result.lower() or "&lt;" in result


def test_step5_renders_markdown_image_as_img_tag():
    module = _load_module()
    md = """## Segment 1

![](images/000004.jpg){.h1}

**中文译文**

![](images/000004.jpg){.h1}

---
"""
    html = module.render_alternating_bilingual_html(md)
    assert '<img src="images/000004.jpg"' in html
    assert "![](images/000004.jpg){.h1}" not in html


def test_step5_renders_heading_tag_and_strips_md_attr_suffix():
    module = _load_module()
    md = """## Segment 1

# Contents ![](images/000002.jpg){.halfem} {#contents .x01-fm-head}

**中文译文**

目录

---
"""
    html = module.render_alternating_bilingual_html(md)
    assert '<h1 class="source-text"' in html
    assert ">Contents" in html
    assert "{#contents .x01-fm-head}" not in html


def test_step5_keeps_translated_headings_out_of_document_outline():
    module = _load_module()
    md = """## Segment 1

# ONE

**中文译文**

# 一

---
"""
    html = module.render_alternating_bilingual_html(md)
    assert '<h1 class="source-text"' in html
    assert '<h1 class="translated-text"' not in html
    assert '<p class="translated-text">一</p>' in html
