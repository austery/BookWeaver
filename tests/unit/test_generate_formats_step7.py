from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


def _load_module() -> types.ModuleType:
    project_root = Path(__file__).resolve().parents[2]
    file_path = project_root / "07_generate_formats.py"
    spec = importlib.util.spec_from_file_location("step7_module", file_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load 07_generate_formats.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_step7_parse_arguments_accepts_output_format(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_step7_resolve_output_formats_for_epub() -> None:
    module = _load_module()
    assert module.resolve_output_formats("epub") == ["epub"]


def test_step7_resolve_output_formats_for_html() -> None:
    module = _load_module()
    assert module.resolve_output_formats("html") == []


def test_step7_resolve_html_input_prefers_book_html_when_book_doc_missing(temp_dir: Path) -> None:
    module = _load_module()
    (temp_dir / "book.html").write_text("<html></html>", encoding="utf-8")
    selected = module.resolve_html_input_file(str(temp_dir))
    assert selected.endswith("book.html")


def test_step7_generate_epub_uses_ebook_convert(
    monkeypatch: pytest.MonkeyPatch, temp_dir: Path
) -> None:
    module = _load_module()
    html_file = temp_dir / "book.html"
    html_file.write_text("<html></html>", encoding="utf-8")
    output_file = temp_dir / "book.epub"

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool, capture_output: bool, text: bool) -> object:
        calls.append(cmd)
        output_file.write_text("ok", encoding="utf-8")
        return type("Result", (), {"stdout": "done"})()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    generated = module.generate_epub_with_script(str(html_file), str(temp_dir), {})
    assert generated == str(output_file)
    assert calls
    assert calls[0][0] == "ebook-convert"


def test_run_ebook_convert_not_installed_returns_false(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "step7", Path(__file__).resolve().parents[2] / "07_generate_formats.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    import subprocess

    def fake_run(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError("ebook-convert: command not found")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = module._run_ebook_convert("input.html", "output.epub")
    assert result is False
    captured = capsys.readouterr()
    assert "ebook-convert not found" in captured.out or "ebook-convert not found" in captured.err


def test_run_ebook_convert_called_process_error_returns_false(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import importlib.util
    import subprocess
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "step7", Path(__file__).resolve().parents[2] / "07_generate_formats.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def fake_run(*args: object, **kwargs: object) -> object:
        raise subprocess.CalledProcessError(
            returncode=1, cmd="ebook-convert", stderr="Conversion error detail"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = module._run_ebook_convert("input.html", "output.epub")
    assert result is False
    captured = capsys.readouterr()
    assert "Conversion error detail" in captured.out or "Conversion error detail" in captured.err
