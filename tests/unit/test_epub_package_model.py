from __future__ import annotations

from pathlib import Path
import tempfile
import zipfile
import pytest


def _build_min_epub(path: Path, cover_item_id: str = "cover-image") -> None:
    with zipfile.ZipFile(path, "w") as zip_file:
        zip_file.writestr("mimetype", "application/epub+zip")
        zip_file.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""",
        )
        zip_file.writestr(
            "content.opf",
            f"""<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Demo</dc:title><dc:language>en</dc:language><dc:identifier id="uid">id</dc:identifier>
    <meta name="cover" content="{cover_item_id}"/>
  </metadata>
  <manifest>
    <item id="cover-image" href="cover.jpg" media-type="image/jpeg"/>
    <item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="toc"><itemref idref="c1"/></spine>
  <guide><reference type="cover" title="Cover" href="chapter1.xhtml"/></guide>
</package>""",
        )
        zip_file.writestr(
            "chapter1.xhtml",
            "<html xmlns='http://www.w3.org/1999/xhtml'><body><h1 id='c1'>Chapter</h1></body></html>",
        )
        zip_file.writestr("toc.ncx", "<ncx></ncx>")
        zip_file.writestr("cover.jpg", "x")


def test_load_epub_package_extracts_cover_and_spine() -> None:
    from ai.epub_package import load_epub_package

    with tempfile.TemporaryDirectory() as temp_dir:
        epub_path = Path(temp_dir) / "book.epub"
        _build_min_epub(epub_path)
        model = load_epub_package(epub_path)
        assert model.opf_path == "content.opf"
        assert model.cover_item_id == "cover-image"
        assert model.spine_itemrefs == ["c1"]


def test_validate_package_structure_detects_missing_cover_item() -> None:
    from ai.epub_package import load_epub_package, validate_package_structure

    with tempfile.TemporaryDirectory() as temp_dir:
        epub_path = Path(temp_dir) / "broken-cover.epub"
        _build_min_epub(epub_path, cover_item_id="missing-cover")

        model = load_epub_package(epub_path)
        report = validate_package_structure(model)
        assert any("cover" in error for error in report.errors)


def test_repack_epub_requires_mimetype_file() -> None:
    from ai.epub_package import repack_epub

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "no-mimetype.epub"
        output_epub = Path(temp_dir) / "out.epub"
        with zipfile.ZipFile(source_epub, "w") as zip_file:
            zip_file.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""",
            )
            zip_file.writestr("content.opf", "<package></package>")

        with pytest.raises(ValueError, match="mimetype"):
            repack_epub(source_epub, output_epub)
