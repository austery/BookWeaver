"""EPUB source Interface behavior through real synthetic packages."""

from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

import pytest

from ai.adapters.sources.epub_adapter import EpubSourceAdapter
from ai.ports.source import TranslatedSegment


def make_package(path: Path, *, empty: bool = False, media_type: str = "text/html") -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>',
        )
        archive.writestr(
            "OEBPS/content.opf",
            f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata/><manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/><item id="two" href="two.html" media-type="{media_type}"/><item id="bib" href="bib.xhtml" media-type="application/xhtml+xml"/><item id="image" href="cover.png" media-type="image/png"/></manifest><spine><itemref idref="two"/><itemref idref="missing"/><itemref idref="image"/><itemref idref="one"/><itemref idref="bib"/></spine></package>',
        )
        bodies = {
            "one.xhtml": '<p><a id="anchor"/>The gate opened.</p><p>Then it closed.</p><table><tr><td>Table stays unchanged.</td></tr></table>',
            "two.html": "<p>The moon rose.</p>",
            "bib.xhtml": "<h1>Bibliography</h1><p>Source Author. Reference Title.</p>",
        }
        for name, body in bodies.items():
            archive.writestr(
                f"OEBPS/{name}",
                '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Example</title></head><body>'
                + ("" if empty else body)
                + "</body></html>",
            )
        archive.writestr("OEBPS/cover.png", b"synthetic image bytes")
        archive.writestr("OEBPS/style.css", "p { color: black; }")


@pytest.mark.parametrize("media_type", ["application/xhtml+xml", "text/html"])
def test_spine_order_stable_ids_and_metadata(tmp_path: Path, media_type: str) -> None:
    source = tmp_path / "book.epub"
    make_package(source, media_type=media_type)
    adapter = EpubSourceAdapter(source)
    segments = adapter.get_segments()
    assert [(s.id, s.text) for s in segments] == [
        ("OEBPS/two.html::0", "The moon rose."),
        ("OEBPS/one.xhtml::0", "The gate opened."),
        ("OEBPS/one.xhtml::1", "Then it closed."),
    ]
    assert segments[1].metadata == {"doc_path": "OEBPS/one.xhtml", "index": 0, "tag_name": "p"}
    assert adapter.get_segments() == segments


def test_reordered_translations_patch_correct_documents_and_preserve_assets(tmp_path: Path) -> None:
    source, output = tmp_path / "book.epub", tmp_path / "out.epub"
    make_package(source)
    before = source.read_bytes()
    adapter = EpubSourceAdapter(source)
    segments = adapter.get_segments()
    translations = ["月亮升起。", "大门打开了。", "然后关闭了。"]
    adapter.apply_translations(
        list(
            reversed(
                [
                    TranslatedSegment(s.id, s.text, text)
                    for s, text in zip(segments, translations, strict=True)
                ]
            )
        )
    )
    adapter.save(str(output))
    assert source.read_bytes() == before
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(output) as result:
        assert result.namelist() == original.namelist()
        for name in original.namelist():
            if name not in {"OEBPS/one.xhtml", "OEBPS/two.html"}:
                assert result.read(name) == original.read(name)
        first = ET.fromstring(result.read("OEBPS/one.xhtml"))
        text = "".join(first.itertext())
        assert (
            text.index("The gate opened.")
            < text.index("大门打开了。")
            < text.index("Then it closed.")
            < text.index("然后关闭了。")
        )
        assert first.find('.//{http://www.w3.org/1999/xhtml}a[@id="anchor"]') is not None
        assert first.find(".//{http://www.w3.org/1999/xhtml}td").text == "Table stays unchanged."
        assert "月亮升起。" in result.read("OEBPS/two.html").decode()


def test_empty_publication_rebuild_keeps_every_entry(tmp_path: Path) -> None:
    source, output = tmp_path / "book.epub", tmp_path / "out.epub"
    make_package(source, empty=True)
    adapter = EpubSourceAdapter(source)
    assert adapter.get_segments() == []
    adapter.save(str(output))
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(output) as result:
        assert result.namelist() == original.namelist()
        assert all(result.read(name) == original.read(name) for name in original.namelist())


def test_invalid_package_fails_without_output(tmp_path: Path) -> None:
    source = tmp_path / "broken.epub"
    source.write_bytes(b"not a ZIP")
    with pytest.raises(zipfile.BadZipFile):
        EpubSourceAdapter(source).get_segments()
    assert not (tmp_path / "out.epub").exists()


def test_output_filesystem_failure_propagates(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_package(source)
    adapter = EpubSourceAdapter(source)
    adapter.get_segments()
    with pytest.raises(IsADirectoryError):
        adapter.save(str(tmp_path))
