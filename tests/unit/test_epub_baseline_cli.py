from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import zipfile


def test_translatebook_help_includes_epub_baseline_mode() -> None:
    content = Path("translatebook.sh").read_text(encoding="utf-8")
    assert "--epub-baseline" in content


def test_roundtrip_script_exists() -> None:
    assert Path("08_epub_roundtrip_baseline.py").exists()


def test_translatebook_help_includes_epub_translate_roundtrip_mode() -> None:
    content = Path("translatebook.sh").read_text(encoding="utf-8")
    assert "--epub-translate-roundtrip" in content
    assert "--checkpoint-dir" in content


def test_translate_roundtrip_script_exists() -> None:
    assert Path("09_epub_translate_roundtrip.py").exists()


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


def test_epub_baseline_dry_run_does_not_require_translation_dependencies() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        input_epub = Path(temp_dir) / "book.epub"
        _build_min_epub(input_epub)

        env = dict(os.environ)
        env["PATH"] = "/usr/bin:/bin"
        completed = subprocess.run(
            ["/bin/bash", "translatebook.sh", "--dry-run", "--epub-baseline", str(input_epub)],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

        assert completed.returncode == 0
        assert "[STEP baseline]" in completed.stdout


def test_translatebook_help_includes_workflow_flag() -> None:
    content = Path("translatebook.sh").read_text(encoding="utf-8")
    assert "--workflow" in content
