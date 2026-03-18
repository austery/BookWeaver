from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import zipfile

import pytest


def _translate_with_batch_separator(text: str) -> str:
    if "%%" in text:
        parts = [part.strip() for part in text.split("\n\n%%\n\n")]
        return "\n\n%%\n\n".join(f"ZH:{part}" for part in parts)
    return f"ZH:{text}"


def _build_min_epub(
    path: Path,
    *,
    broken_fragment: bool = False,
    paragraphs: list[str] | None = None,
) -> None:
    fragment = "missing" if broken_fragment else "anchor"
    body_paragraphs = paragraphs or ["Hello."]
    body_html = "".join(f"<p>{text}</p>" for text in body_paragraphs)
    with zipfile.ZipFile(path, "w") as zip_file:
        zip_file.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zip_file.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""",
        )
        zip_file.writestr(
            "content.opf",
            """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Demo</dc:title><dc:language>en</dc:language><dc:identifier id="uid">id</dc:identifier>
    <meta name="cover" content="cover-image"/>
  </metadata>
  <manifest>
    <item id="cover-image" href="cover.jpg" media-type="image/jpeg"/>
    <item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="toc"><itemref idref="c1"/></spine>
</package>""",
        )
        zip_file.writestr(
            "chapter1.xhtml",
            (
                "<html xmlns='http://www.w3.org/1999/xhtml'>"
                f"<body><a href='chapter1.xhtml#{fragment}'>go</a>"
                "<p id='anchor'>Anchor</p>"
                f"{body_html}</body></html>"
            ),
        )
        zip_file.writestr("toc.ncx", "<ncx><navMap></navMap></ncx>")
        zip_file.writestr("cover.jpg", "x")


def test_translate_roundtrip_rewrites_spine_xhtml_and_preserves_toc_file() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book.epub"
        output_epub = Path(temp_dir) / "translated.epub"
        _build_min_epub(source_epub)

        with zipfile.ZipFile(source_epub, "r") as source_zip:
            toc_before = source_zip.read("toc.ncx")

        result = run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=_translate_with_batch_separator,
        )

        assert result.output_epub.exists()
        assert result.translated_segments > 0

        with zipfile.ZipFile(output_epub, "r") as output_zip:
            toc_after = output_zip.read("toc.ncx")
            chapter = output_zip.read("chapter1.xhtml").decode("utf-8")

        assert toc_before == toc_after
        assert "Hello." in chapter
        assert "ZH:Hello." in chapter


def test_translate_roundtrip_fails_on_integrity_error() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-broken.epub"
        output_epub = Path(temp_dir) / "translated-broken.epub"
        _build_min_epub(source_epub, broken_fragment=True)

        with pytest.raises(RuntimeError, match="broken fragment"):
            run_translate_roundtrip(
                source_epub=source_epub,
                output_epub=output_epub,
                output_lang="zh",
                bilingual_style="alternating",
                model="gemini-2.5-flash",
                custom_prompt=None,
                translate_fn=lambda text: f"ZH:{text}",
            )


def test_translate_roundtrip_uses_batch_call_per_doc() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-batch.epub"
        output_epub = Path(temp_dir) / "translated-batch.epub"
        _build_min_epub(source_epub, paragraphs=["P1", "P2", "P3"])

        call_count = 0

        def batch_translate(text: str) -> str:
            nonlocal call_count
            call_count += 1
            return _translate_with_batch_separator(text)

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=batch_translate,
        )

        assert call_count == 1


def test_translate_roundtrip_retries_with_split_on_batch_mismatch() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-retry.epub"
        output_epub = Path(temp_dir) / "translated-retry.epub"
        _build_min_epub(source_epub, paragraphs=["A", "B", "C", "D"])

        calls: list[str] = []
        mismatch_injected = False

        def flaky_batch_translate(text: str) -> str:
            nonlocal mismatch_injected
            calls.append(text)
            if "%%" not in text:
                return _translate_with_batch_separator(text)
            if not mismatch_injected:
                mismatch_injected = True
                return "BROKEN"
            return _translate_with_batch_separator(text)

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=flaky_batch_translate,
        )

        assert any("%%" in payload for payload in calls)
        assert len(calls) > 1


def test_translate_roundtrip_retries_with_split_on_batch_timeout() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-timeout.epub"
        output_epub = Path(temp_dir) / "translated-timeout.epub"
        _build_min_epub(source_epub, paragraphs=["A", "B", "C", "D"])

        calls: list[str] = []
        timeout_injected = False

        def timeout_then_translate(text: str) -> str:
            nonlocal timeout_injected
            calls.append(text)
            if "%%" in text and not timeout_injected:
                timeout_injected = True
                raise subprocess.TimeoutExpired(cmd=["gemini", "--model", "gemini-3-pro-preview"], timeout=180)
            return _translate_with_batch_separator(text)

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=timeout_then_translate,
        )

        assert timeout_injected
        assert len(calls) > 1
