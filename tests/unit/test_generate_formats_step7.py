from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    project_root = Path(__file__).resolve().parents[2]
    file_path = project_root / "07_generate_formats.py"
    spec = importlib.util.spec_from_file_location("step7_module", file_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load 07_generate_formats.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_step7_parse_arguments_accepts_output_format(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "07_generate_formats.py",
            "--temp-dir",
            "/tmp/demo",
            "--output-format",
            "epub",
        ],
    )
    args = module.parse_arguments()
    assert args.temp_dir == "/tmp/demo"
    assert args.output_format == "epub"


def test_step7_resolve_output_formats_for_epub():
    module = _load_module()
    assert module.resolve_output_formats("epub") == ["epub"]


def test_step7_resolve_output_formats_for_html():
    module = _load_module()
    assert module.resolve_output_formats("html") == []


def test_step7_resolve_html_input_prefers_book_html_when_book_doc_missing(temp_dir):
    module = _load_module()
    (temp_dir / "book.html").write_text("<html></html>", encoding="utf-8")
    selected = module.resolve_html_input_file(str(temp_dir))
    assert selected.endswith("book.html")


def test_step7_generate_epub_uses_ebook_convert(monkeypatch, temp_dir):
    module = _load_module()
    html_file = temp_dir / "book.html"
    html_file.write_text("<html></html>", encoding="utf-8")
    output_file = temp_dir / "book.epub"

    calls = []

    def fake_run(cmd, check, capture_output, text):
        calls.append(cmd)
        output_file.write_text("ok", encoding="utf-8")
        return type("Result", (), {"stdout": "done"})()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    generated = module.generate_epub_with_script(str(html_file), str(temp_dir), {})
    assert generated == str(output_file)
    assert calls
    assert calls[0][0] == "ebook-convert"
