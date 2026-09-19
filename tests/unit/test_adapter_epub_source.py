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


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("stage", ["write", "file_sync", "replace", "directory_sync"])
def test_atomic_save_failure_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing: bool, stage: str
) -> None:
    import os
    import stat
    from unittest.mock import patch

    source, output = tmp_path / "book.epub", tmp_path / "out.epub"
    make_package(source)
    original_source = source.read_bytes()
    previous = b"previous complete output"
    if existing:
        output.write_bytes(previous)
    adapter = EpubSourceAdapter(source)
    adapter.get_segments()
    real_sync = os.fsync

    def sync(descriptor: int) -> None:
        directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
        if (stage == "file_sync" and not directory) or (stage == "directory_sync" and directory):
            raise OSError("injected sync failure")
        real_sync(descriptor)

    monkeypatch.setattr(os, "fsync", sync)
    with patch("ai.epub_package.os.replace", wraps=os.replace) as replace:
        if stage == "replace":
            replace.side_effect = OSError("injected replacement failure")
        with patch.object(zipfile.ZipFile, "writestr", autospec=True) as write:
            # Preserve real writes except for a failure after the first complete entry.
            write.side_effect = real_write = _REAL_ZIP_WRITE
            if stage == "write":

                def fail_write(
                    archive: zipfile.ZipFile, info: zipfile.ZipInfo, data: bytes
                ) -> None:
                    if info.filename != "mimetype":
                        raise OSError("injected entry failure")
                    real_write(archive, info, data)

                write.side_effect = fail_write
            with pytest.raises(OSError) as caught:
                adapter.save(str(output))
    assert source.read_bytes() == original_source
    assert not list(tmp_path.glob(".bookweaver-epub-*"))
    if stage == "directory_sync":
        assert "output was replaced, but durability is unconfirmed" in str(caught.value)
        with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
            assert before.namelist() == after.namelist()
            assert all(before.read(name) == after.read(name) for name in before.namelist())
    elif existing:
        assert output.read_bytes() == previous
    else:
        assert not output.exists()


_REAL_ZIP_WRITE = zipfile.ZipFile.writestr


def test_successful_save_replaces_existing_output(tmp_path: Path) -> None:
    source, output = tmp_path / "book.epub", tmp_path / "out.epub"
    make_package(source)
    output.write_bytes(b"previous output")
    adapter = EpubSourceAdapter(source)
    adapter.get_segments()
    adapter.save(str(output))
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
        assert before.namelist() == after.namelist()
        assert all(before.read(name) == after.read(name) for name in before.namelist())
    assert not list(tmp_path.glob(".bookweaver-epub-*"))


def test_directory_close_failure_does_not_mask_sync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import stat

    source, output = tmp_path / "book.epub", tmp_path / "out.epub"
    make_package(source)
    adapter = EpubSourceAdapter(source)
    real_sync, real_close = os.fsync, os.close
    sync_error = OSError("primary directory sync failure")

    def sync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise sync_error
        real_sync(descriptor)

    def close(descriptor: int) -> None:
        directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
        real_close(descriptor)
        if directory:
            raise OSError("secondary directory close failure")

    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(os, "close", close)
    with pytest.raises(OSError, match="output was replaced") as caught:
        adapter.save(str(output))
    assert caught.value.__cause__ is sync_error
    assert "secondary directory close failure" in sync_error.__notes__[0]
    assert zipfile.is_zipfile(output)


def test_temporary_cleanup_failure_does_not_mask_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import patch

    source, output = tmp_path / "book.epub", tmp_path / "out.epub"
    make_package(source)
    output.write_bytes(b"old output")
    adapter = EpubSourceAdapter(source)
    primary = OSError("primary replacement failure")
    with patch("ai.epub_package.os.replace", side_effect=primary):
        with patch.object(Path, "unlink", side_effect=OSError("secondary cleanup failure")):
            with pytest.raises(OSError) as caught:
                adapter.save(str(output))
    assert caught.value is primary
    assert "secondary cleanup failure" in primary.__notes__[0]
    assert output.read_bytes() == b"old output"
