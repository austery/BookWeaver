from __future__ import annotations

import subprocess
import tempfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _build_min_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zip_file:
        zip_file.writestr(
            "mimetype",
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
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
            "<html xmlns='http://www.w3.org/1999/xhtml'><body><h1 id='c1'>Chapter</h1></body></html>",
        )
        zip_file.writestr("toc.ncx", "<ncx></ncx>")
        zip_file.writestr("cover.jpg", "x")


def test_old_roundtrip_flag_maps_to_epub_workflow_with_warning() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        input_epub = Path(temp_dir) / "book.epub"
        _build_min_epub(input_epub)
        completed = subprocess.run(
            [
                "/bin/bash",
                "translatebook.sh",
                "--dry-run",
                "--epub-translate-roundtrip",
                str(input_epub),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0
        assert "Resolved workflow: epub" in completed.stdout
        assert "deprecated" in completed.stdout.lower()


def test_conflicting_workflow_and_old_roundtrip_flag_fails() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        input_epub = Path(temp_dir) / "book.epub"
        _build_min_epub(input_epub)
        completed = subprocess.run(
            [
                "/bin/bash",
                "translatebook.sh",
                "--dry-run",
                "--workflow",
                "markdown",
                "--epub-translate-roundtrip",
                str(input_epub),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 2
        assert "conflict" in f"{completed.stdout}\n{completed.stderr}".lower()


def test_provider_api_flag_is_accepted_in_dry_run() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        input_epub = Path(temp_dir) / "book.epub"
        _build_min_epub(input_epub)
        completed = subprocess.run(
            [
                "/bin/bash",
                "translatebook.sh",
                "--dry-run",
                "--workflow",
                "epub",
                "--provider",
                "api",
                str(input_epub),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0
        assert "Provider: api" in completed.stdout
