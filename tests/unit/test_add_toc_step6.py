from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_step6_module():
    project_root = Path(__file__).resolve().parents[2]
    file_path = project_root / "06_add_toc.py"
    spec = importlib.util.spec_from_file_location("step6_module", file_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load 06_add_toc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_step6_regex_extracts_markdown_heading_paragraph_and_inserts_toc(temp_dir: Path):
    module = _load_step6_module()
    html_file = temp_dir / "book.html"
    html_file.write_text(
        (
            "<html><body>"
            '<p class="source-text"># Chapter 1</p>'
            '<p class="translated-text"># 第一章</p>'
            '<p class="source-text">body</p>'
            "</body></html>"
        ),
        encoding="utf-8",
    )

    ok = module.insert_toc_with_regex(str(html_file))
    assert ok is True

    updated = html_file.read_text(encoding="utf-8")
    assert 'class="toc-content"' in updated
    assert 'href="#chapter-1"' in updated
    assert 'id="chapter-1"' in updated
    assert 'href="#第一章"' not in updated


def test_step6_insert_toc_into_html_uses_regex_fallback(monkeypatch, temp_dir: Path):
    module = _load_step6_module()
    monkeypatch.setattr(module, "BS4_AVAILABLE", False)
    html_file = temp_dir / "book.html"
    html_file.write_text(
        "<html><body><p class='source-text'># Intro</p><p>content</p></body></html>",
        encoding="utf-8",
    )

    ok = module.insert_toc_into_html(str(html_file))
    assert ok is True
    updated = html_file.read_text(encoding="utf-8")
    assert 'href="#intro"' in updated


def test_step6_parse_markdown_heading_strips_image_and_attr_suffix():
    module = _load_step6_module()
    parsed = module.parse_markdown_heading(
        "# Contents ![](images/000002.jpg){.halfem} {#contents .x01-fm-head}"
    )
    assert parsed == (1, "Contents")


def test_step6_toc_includes_only_h1_headings_in_regex_mode(temp_dir: Path):
    module = _load_step6_module()
    html_file = temp_dir / "book.html"
    html_file.write_text(
        (
            "<html><body>"
            '<div class="toc-content"></div>'
            '<h1 class="source-text">Chapter</h1>'
            '<h3 class="source-text">Subsection</h3>'
            "</body></html>"
        ),
        encoding="utf-8",
    )
    ok = module.insert_toc_with_regex(str(html_file))
    assert ok is True
    updated = html_file.read_text(encoding="utf-8")
    assert 'href="#chapter"' in updated
    assert 'href="#subsection"' not in updated
