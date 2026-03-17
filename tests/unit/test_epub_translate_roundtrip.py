from __future__ import annotations

from pathlib import Path
import tempfile
import zipfile

import pytest


def _build_min_epub(path: Path, *, broken_fragment: bool = False) -> None:
    fragment = "missing" if broken_fragment else "anchor"
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
            f"<html xmlns='http://www.w3.org/1999/xhtml'><body><a href='chapter1.xhtml#{fragment}'>go</a><p id='anchor'>Hello.</p></body></html>",
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
            translate_fn=lambda text: f"ZH:{text}",
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
