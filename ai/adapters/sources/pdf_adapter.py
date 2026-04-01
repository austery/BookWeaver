"""PDF source adapter using Calibre HTMLZ conversion + markdown delegation.

Self-contained adapter (no imports from legacy 01-09 scripts).
Pipeline:
1) ebook-convert PDF -> HTMLZ
2) extract HTML(+images) from HTMLZ zip
3) convert HTML -> markdown via pypandoc
4) clean Calibre-specific markers
5) split markdown into page*.md chunks
6) delegate segment handling to MarkdownSourceAdapter
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from pathlib import Path

from ai.adapters.sources.markdown_adapter import MarkdownSourceAdapter
from ai.ports.source import IBookSource, Segment, TranslatedSegment


def _find_ebook_convert() -> str:
    candidates = [
        "/Applications/calibre.app/Contents/MacOS/ebook-convert",
        "/usr/bin/ebook-convert",
        "/usr/local/bin/ebook-convert",
        "ebook-convert",
    ]
    for cmd in candidates:
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    raise FileNotFoundError("Calibre ebook-convert not found")


def _convert_to_htmlz(input_pdf: Path, htmlz_path: Path, calibre_cmd: str) -> None:
    result = subprocess.run(
        [calibre_cmd, str(input_pdf), str(htmlz_path)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        msg = (result.stderr or "").strip() or "unknown error"
        raise RuntimeError(f"HTMLZ conversion failed: {msg}")
    if not htmlz_path.exists():
        raise FileNotFoundError(f"Expected HTMLZ not created: {htmlz_path}")


def _extract_htmlz_archive(htmlz_path: Path, extract_dir: Path) -> tuple[Path, Path | None]:
    try:
        with zipfile.ZipFile(htmlz_path, "r") as zf:
            zf.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"Invalid HTMLZ archive: {exc}") from exc

    html_file: Path | None = None
    images_dir: Path | None = None

    for p in extract_dir.rglob("*"):
        if p.is_file() and p.name.lower() in {"index.html", "index.htm"}:
            html_file = p
            break

    if html_file is None:
        for p in extract_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".html", ".htm"}:
                html_file = p
                break

    for p in extract_dir.rglob("*"):
        if p.is_dir() and p.name.lower() in {"images", "image", "pics", "pictures"}:
            images_dir = p
            break

    if html_file is None:
        raise FileNotFoundError("No HTML file found in extracted HTMLZ")
    return html_file, images_dir


def _extract_opf_metadata(extract_dir: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    opf_file: Path | None = None
    for p in extract_dir.rglob("*"):
        if p.is_file() and p.name.lower() == "metadata.opf":
            opf_file = p
            break
    if opf_file is None:
        return metadata

    try:
        tree = ET.parse(opf_file)
        root = tree.getroot()
    except ET.ParseError:
        return metadata

    ns = {
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    title = root.find(".//dc:title", ns)
    creator = root.find(".//dc:creator", ns)
    publisher = root.find(".//dc:publisher", ns)
    language = root.find(".//dc:language", ns)
    if title is not None and title.text:
        metadata["title"] = title.text.strip()
    if creator is not None and creator.text:
        metadata["creator"] = creator.text.strip()
    if publisher is not None and publisher.text:
        metadata["publisher"] = publisher.text.strip()
    if language is not None and language.text:
        metadata["language"] = language.text.strip()
    return metadata


def _default_extract_htmlz_archive(htmlz_path: Path, extract_dir: Path) -> tuple[Path, Path | None]:
    return _extract_htmlz_archive(htmlz_path, extract_dir)


def _default_extract_opf_metadata(extract_dir: Path) -> dict[str, str]:
    return _extract_opf_metadata(extract_dir)


def _clean_calibre_markers(content: str) -> str:
    import re

    content = re.sub(r"\{\.calibre[^}]*\}", "", content)
    content = re.sub(r"\(#calibre_link-\d+\)", "", content)

    cleaned_lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(":::"):
            continue
        if stripped.isdigit():
            continue
        if stripped.endswith(".ct}") or stripped.endswith(".cn}"):
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _convert_html_to_markdown(input_html: Path, output_md: Path) -> None:
    try:
        import pypandoc

        pypandoc.convert_file(
            str(input_html),
            "markdown",
            outputfile=str(output_md),
            extra_args=["--wrap=none"],
        )
    except ImportError:
        # Fallback to pandoc CLI if pypandoc is unavailable.
        result = subprocess.run(
            [
                "pandoc",
                str(input_html),
                "-f",
                "html",
                "-t",
                "markdown",
                "-o",
                str(output_md),
                "--wrap=none",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            msg = (result.stderr or "").strip() or "unknown error"
            raise RuntimeError(f"HTML->Markdown conversion failed: {msg}")
    if not output_md.exists():
        raise FileNotFoundError(f"Markdown conversion output missing: {output_md}")

    content = output_md.read_text(encoding="utf-8")
    content = content.replace("\ufeff", "").replace("\u00a0", " ")
    content = _clean_calibre_markers(content)
    output_md.write_text(content, encoding="utf-8")


def _split_markdown_by_size(input_md: Path, output_dir: Path, target_size: int) -> int:
    content = input_md.read_text(encoding="utf-8")
    lines = content.splitlines()

    chunks: list[str] = []
    current_lines: list[str] = []
    current_size = 0
    for line in lines:
        line_size = len(line) + 1
        if current_lines and current_size + line_size > target_size:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
            current_size = line_size
        else:
            current_lines.append(line)
            current_size += line_size
    if current_lines:
        chunks.append("\n".join(current_lines))

    for idx, chunk in enumerate(chunks, start=1):
        (output_dir / f"page{idx:04d}.md").write_text(chunk, encoding="utf-8")
    return len(chunks)


def _write_config_file(
    temp_dir: Path,
    input_file: Path,
    metadata: dict[str, str],
    *,
    input_lang: str = "auto",
    output_lang: str = "zh",
) -> None:
    lines = [
        "# Translation Configuration",
        f"input_file={input_file}",
        f"input_lang={input_lang}",
        f"output_lang={output_lang}",
        "conversion_method=calibre_htmlz",
    ]
    if metadata:
        lines.append("")
        lines.append("# Book Metadata")
        if "title" in metadata:
            lines.append(f"original_title={metadata['title']}")
        if "creator" in metadata:
            lines.append(f"creator={metadata['creator']}")
        if "publisher" in metadata:
            lines.append(f"publisher={metadata['publisher']}")
        if "language" in metadata:
            lines.append(f"source_language={metadata['language']}")
    (temp_dir / "config.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


class PdfSourceAdapter(IBookSource):
    """PDF adapter with persistent `<basename>_temp` workspace."""

    def __init__(
        self,
        pdf_path: str | Path,
        *,
        chunk_size: int = 6000,
        _find_calibre: Callable[[], str] | None = None,
        _convert_htmlz: Callable[[Path, Path, str], None] | None = None,
        _extract_htmlz_archive: Callable[[Path, Path], tuple[Path, Path | None]] | None = None,
        _extract_opf_metadata: Callable[[Path], dict[str, str]] | None = None,
        _html_to_md: Callable[[Path, Path], None] | None = None,
        _split_md: Callable[[Path, Path, int], int] | None = None,
    ) -> None:
        self._pdf_path = Path(pdf_path)
        self._chunk_size = chunk_size
        self._temp_dir = self._pdf_path.parent / f"{self._pdf_path.stem}_temp"

        self._find_calibre = _find_calibre or _find_ebook_convert
        self._convert_htmlz = _convert_htmlz or _convert_to_htmlz
        self._extract_htmlz = _extract_htmlz_archive or _default_extract_htmlz_archive
        self._extract_metadata = _extract_opf_metadata or _default_extract_opf_metadata
        self._html_to_md = _html_to_md or _convert_html_to_markdown
        self._split_md = _split_md or _split_markdown_by_size

        self._md_adapter: MarkdownSourceAdapter | None = None

    def get_segments(self) -> list[Segment]:
        self._ensure_workspace()
        return self._delegate().get_segments()

    def apply_translations(self, translated: list[TranslatedSegment]) -> None:
        self._ensure_workspace()
        self._delegate().apply_translations(translated)

    def save(self, output_path: str) -> None:
        self._ensure_workspace()
        self._delegate().save(output_path)

    def _delegate(self) -> MarkdownSourceAdapter:
        if self._md_adapter is None:
            self._md_adapter = MarkdownSourceAdapter(self._temp_dir)
        return self._md_adapter

    def _ensure_workspace(self) -> None:
        if not self._pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {self._pdf_path}")
        self._temp_dir.mkdir(parents=True, exist_ok=True)

        input_html = self._temp_dir / "input.html"
        input_md = self._temp_dir / "input.md"
        config_file = self._temp_dir / "config.txt"
        source_pages = sorted(
            p for p in self._temp_dir.glob("page*.md") if not p.name.startswith("output_")
        )
        if source_pages and input_md.exists() and config_file.exists():
            return

        if not input_html.exists():
            calibre = self._find_calibre()
            htmlz_path = self._temp_dir / f"{self._pdf_path.stem}.htmlz"
            self._convert_htmlz(self._pdf_path, htmlz_path, calibre)

            with tempfile.TemporaryDirectory() as tmp_extract:
                extract_dir = Path(tmp_extract)
                html_file, images_dir = self._extract_htmlz(htmlz_path, extract_dir)
                metadata = self._extract_metadata(extract_dir)
                shutil.copy2(html_file, input_html)
                if images_dir is not None and images_dir.exists():
                    target_images = self._temp_dir / "images"
                    if not target_images.exists():
                        shutil.copytree(images_dir, target_images)
                _write_config_file(self._temp_dir, self._pdf_path, metadata)

            if htmlz_path.exists():
                htmlz_path.unlink()
        elif not config_file.exists():
            _write_config_file(self._temp_dir, self._pdf_path, {})

        if not input_md.exists():
            self._html_to_md(input_html, input_md)

        source_pages = sorted(
            p for p in self._temp_dir.glob("page*.md") if not p.name.startswith("output_")
        )
        if not source_pages:
            chunk_count = self._split_md(input_md, self._temp_dir, self._chunk_size)
            if chunk_count == 0:
                raise RuntimeError("No markdown chunks generated from PDF")
