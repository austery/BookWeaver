"""Unit tests for PdfSourceAdapter orchestration."""

from __future__ import annotations

from pathlib import Path

from ai.adapters.sources.pdf_adapter import PdfSourceAdapter
from ai.ports.source import TranslatedSegment


def test_pdf_adapter_builds_workspace_and_delegates(tmp_path: Path) -> None:
    pdf_file = tmp_path / "report.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake\n")

    calls: dict[str, int] = {
        "find": 0,
        "convert": 0,
        "extract": 0,
        "meta": 0,
        "html2md": 0,
        "split": 0,
    }

    def fake_find() -> str:
        calls["find"] += 1
        return "ebook-convert"

    def fake_convert(input_pdf: Path, htmlz_path: Path, calibre_cmd: str) -> None:
        calls["convert"] += 1
        assert input_pdf == pdf_file
        assert calibre_cmd == "ebook-convert"
        htmlz_path.write_bytes(b"fake-htmlz")

    def fake_extract(htmlz_path: Path, extract_dir: Path) -> tuple[Path, Path | None]:
        calls["extract"] += 1
        html = extract_dir / "index.html"
        html.write_text("<h1>Hello</h1><p>World</p>", encoding="utf-8")
        images = extract_dir / "images"
        images.mkdir()
        (images / "pic.png").write_bytes(b"\x89PNG")
        return html, images

    def fake_meta(extract_dir: Path) -> dict[str, str]:
        calls["meta"] += 1
        return {"title": "Annual Report", "creator": "ACME"}

    def fake_html2md(input_html: Path, output_md: Path) -> None:
        calls["html2md"] += 1
        assert input_html.exists()
        output_md.write_text("# Hello\n\nWorld", encoding="utf-8")

    def fake_split(input_md: Path, output_dir: Path, chunk_size: int) -> int:
        calls["split"] += 1
        assert chunk_size == 6000
        text = input_md.read_text(encoding="utf-8")
        assert "Hello" in text
        (output_dir / "page0001.md").write_text("# Hello\n\nWorld", encoding="utf-8")
        return 1

    adapter = PdfSourceAdapter(
        pdf_file,
        _find_calibre=fake_find,
        _convert_htmlz=fake_convert,
        _extract_htmlz_archive=fake_extract,
        _extract_opf_metadata=fake_meta,
        _html_to_md=fake_html2md,
        _split_md=fake_split,
    )

    segs = adapter.get_segments()
    assert len(segs) == 2  # heading + paragraph
    assert segs[0].id == "page0001::0"
    assert segs[1].id == "page0001::1"

    adapter.apply_translations(
        [
            TranslatedSegment(id=segs[0].id, original=segs[0].text, translated="# 你好"),
            TranslatedSegment(id=segs[1].id, original=segs[1].text, translated="世界"),
        ]
    )
    out = tmp_path / "out.md"
    adapter.save(str(out))
    content = out.read_text(encoding="utf-8")
    assert "# Hello" in content
    assert "# 你好" in content
    assert "World" in content
    assert "世界" in content

    workspace = tmp_path / "report_temp"
    assert workspace.exists()
    assert (workspace / "input.html").exists()
    assert (workspace / "input.md").exists()
    assert (workspace / "page0001.md").exists()
    assert (workspace / "config.txt").exists()
    assert (workspace / "images").is_dir()

    # Orchestration calls happened exactly once
    assert calls == {
        "find": 1,
        "convert": 1,
        "extract": 1,
        "meta": 1,
        "html2md": 1,
        "split": 1,
    }


def test_pdf_adapter_reuses_existing_workspace_without_reconversion(tmp_path: Path) -> None:
    pdf_file = tmp_path / "report.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake\n")
    workspace = tmp_path / "report_temp"
    workspace.mkdir()
    (workspace / "input.html").write_text("<h1>A</h1>", encoding="utf-8")
    (workspace / "input.md").write_text("A", encoding="utf-8")
    (workspace / "page0001.md").write_text("A", encoding="utf-8")
    (workspace / "config.txt").write_text("conversion_method=calibre_htmlz\n", encoding="utf-8")

    def fail_find() -> str:
        raise AssertionError("should not call calibre finder on cached workspace")

    adapter = PdfSourceAdapter(pdf_file, _find_calibre=fail_find)
    segs = adapter.get_segments()
    assert len(segs) == 1
    assert segs[0].id == "page0001::0"


def test_pdf_adapter_missing_pdf_raises(tmp_path: Path) -> None:
    adapter = PdfSourceAdapter(tmp_path / "missing.pdf")
    try:
        adapter.get_segments()
    except FileNotFoundError as exc:
        assert "PDF not found" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")
