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


def test_fallback_flag_is_accepted_in_dry_run() -> None:
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
                "--fallback-provider",
                "api",
                str(input_epub),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0
        assert "Fallback provider: api" in completed.stdout


def test_epub_dry_run_uses_ai_cli_module_not_legacy_roundtrip_script() -> None:
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
                str(input_epub),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        combined_output = f"{completed.stdout}\n{completed.stderr}"
        assert completed.returncode == 0
        assert "python3 -u -m ai.cli" in combined_output
        assert "--input-format epub" in combined_output
        assert "translated_roundtrip.epub" in combined_output
        assert "09_epub_translate_roundtrip.py" not in combined_output
        assert "--checkpoint-dir" not in combined_output


def test_epub_dry_run_propagates_optional_ai_cli_flags() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        input_epub = Path(temp_dir) / "book.epub"
        glossary_path = Path(temp_dir) / "glossary.json"
        _build_min_epub(input_epub)
        glossary_path.write_text("{}", encoding="utf-8")

        completed = subprocess.run(
            [
                "/bin/bash",
                "translatebook.sh",
                "--dry-run",
                "--workflow",
                "epub",
                "--model",
                "flash",
                "--prompt",
                "keep_style",
                "--glossary",
                str(glossary_path),
                "--glossary-min-priority",
                "high",
                "--fallback-provider",
                "api",
                "--extract-glossary",
                str(input_epub),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        combined_output = f"{completed.stdout}\n{completed.stderr}"
        assert completed.returncode == 0
        assert "--model flash" in combined_output
        assert "-p keep_style" in combined_output
        assert "--glossary" in combined_output
        assert "--glossary-min-priority high" in combined_output
        assert "--cli-api-fallback" in combined_output
        assert "--extract-glossary" in combined_output


def test_epub_dry_run_force_resume_is_warned_as_ignored() -> None:
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
                "--force-resume",
                str(input_epub),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        combined_output = f"{completed.stdout}\n{completed.stderr}".lower()
        assert completed.returncode == 0
        assert "force-resume" in combined_output
        assert "ignored" in combined_output


def test_markdown_dry_run_step3_uses_ai_cli_and_step4_is_skipped() -> None:
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
                str(input_epub),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        combined_output = f"{completed.stdout}\n{completed.stderr}"
        assert completed.returncode == 0
        assert "python3 -u -m ai.cli" in combined_output
        assert "--input-format markdown" in combined_output
        assert "output.md" in combined_output
        assert "03_translate_md.py" not in combined_output
        assert "Step 4" in combined_output
        assert "skip" in combined_output.lower()


def test_markdown_dry_run_propagates_optional_ai_cli_flags() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        input_epub = Path(temp_dir) / "book.epub"
        glossary_path = Path(temp_dir) / "glossary.json"
        _build_min_epub(input_epub)
        glossary_path.write_text("{}", encoding="utf-8")
        completed = subprocess.run(
            [
                "/bin/bash",
                "translatebook.sh",
                "--dry-run",
                "--workflow",
                "markdown",
                "--model",
                "pro",
                "--prompt",
                "preserve_terms",
                "--glossary",
                str(glossary_path),
                "--glossary-min-priority",
                "critical",
                "--fallback-provider",
                "api",
                str(input_epub),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        combined_output = f"{completed.stdout}\n{completed.stderr}"
        assert completed.returncode == 0
        assert "--input-format markdown" in combined_output
        assert "--model pro" in combined_output
        assert "-p preserve_terms" in combined_output
        assert "--glossary" in combined_output
        assert "--glossary-min-priority critical" in combined_output
        assert "--cli-api-fallback" in combined_output


def test_markdown_dry_run_propagates_glossary_max_terms() -> None:
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
                "--extract-glossary",
                "--glossary-max-terms",
                "18",
                str(input_epub),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        combined_output = f"{completed.stdout}\n{completed.stderr}"
        assert completed.returncode == 0
        assert "--glossary-max-terms 18" in combined_output


def test_no_skip_flag_warns_as_ignored() -> None:
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
                "--no-skip",
                str(input_epub),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        combined_output = f"{completed.stdout}\n{completed.stderr}".lower()
        assert completed.returncode == 0
        assert "--no-skip" in combined_output
        assert "ignored" in combined_output


def test_markdown_api_provider_dry_run_no_gemini_dependency_error() -> None:
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
                "--provider",
                "api",
                str(input_epub),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
            check=False,
        )
        combined_output = f"{completed.stdout}\n{completed.stderr}"
        assert completed.returncode == 0
        assert "Gemini CLI not found" not in combined_output
