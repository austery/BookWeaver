#!/usr/bin/env python3
"""Generate a minimal, valid test EPUB for E2E dual-targeting tests.

Produces test_book.epub in the current directory (or the path given as
an optional first CLI argument).  The EPUB contains two short chapters
with basic HTML formatting so we can verify:
  - Bilingual alternating injection works for each paragraph
  - Bold/italic tags are preserved across the pipeline
  - Multi-chapter documents are handled correctly

Usage:
    python generate_test_epub.py [output_path]
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

# ── EPUB skeleton content ────────────────────────────────────

_MIMETYPE = "application/epub+zip"

_CONTAINER_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0"
           xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf"
              media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_CONTENT_OPF = """\
<?xml version="1.0" encoding="UTF-8"?>
<package version="3.0" unique-identifier="book-id"
         xmlns="http://www.idpf.org/2007/opf"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <metadata>
    <dc:identifier id="book-id">urn:uuid:test-book-hexagonal-spec012</dc:identifier>
    <dc:title>The Hexagonal Test Book</dc:title>
    <dc:language>en</dc:language>
    <dc:creator>BookWeaver Test Suite</dc:creator>
  </metadata>
  <manifest>
    <item id="ncx"       href="toc.ncx"       media-type="application/x-dtbncx+xml"/>
    <item id="nav"       href="nav.xhtml"     media-type="application/xhtml+xml"
          properties="nav"/>
    <item id="chapter1"  href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="chapter2"  href="chapter2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="chapter1"/>
    <itemref idref="chapter2"/>
  </spine>
</package>
"""

_TOC_NCX = """\
<?xml version="1.0" encoding="UTF-8"?>
<ncx version="2005-1" xmlns="http://www.daisy.org/z3986/2005/ncx/">
  <head>
    <meta name="dtb:uid" content="urn:uuid:test-book-hexagonal-spec012"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNormal" content="0"/>
  </head>
  <docTitle><text>The Hexagonal Test Book</text></docTitle>
  <navMap>
    <navPoint id="np-1" playOrder="1">
      <navLabel><text>Chapter 1: Ports and Adapters</text></navLabel>
      <content src="chapter1.xhtml"/>
    </navPoint>
    <navPoint id="np-2" playOrder="2">
      <navLabel><text>Chapter 2: The Core Domain</text></navLabel>
      <content src="chapter2.xhtml"/>
    </navPoint>
  </navMap>
</ncx>
"""

_NAV_XHTML = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops" lang="en">
  <head><meta charset="UTF-8"/><title>Table of Contents</title></head>
  <body>
    <nav epub:type="toc">
      <ol>
        <li><a href="chapter1.xhtml">Chapter 1: Ports and Adapters</a></li>
        <li><a href="chapter2.xhtml">Chapter 2: The Core Domain</a></li>
      </ol>
    </nav>
  </body>
</html>
"""

# Chapter 1: plain and formatted paragraphs
_CHAPTER1_XHTML = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
  <head><meta charset="UTF-8"/><title>Chapter 1</title></head>
  <body>
    <h1>Chapter 1: Ports and Adapters</h1>
    <p>The hexagonal architecture, also known as the Ports and Adapters
    pattern, was introduced by Alistair Cockburn in 2005. Its central
    idea is to isolate the application core from external concerns.</p>
    <p>A <b>port</b> defines an interface — a contract that the core
    expects to be satisfied, without knowing the concrete implementation
    behind it. This is the Dependency Inversion Principle in action.</p>
    <p>An <i>adapter</i> is the concrete implementation that connects
    an external technology (a database, a CLI tool, an HTTP client) to
    the port interface the core depends on.</p>
    <p>The result is a system where the <b>business logic</b> can be
    tested in complete isolation from <i>infrastructure concerns</i>
    — no real API calls, no real file I/O required in unit tests.</p>
  </body>
</html>
"""

# Chapter 2: list items and mixed formatting to stress-test adapters
_CHAPTER2_XHTML = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
  <head><meta charset="UTF-8"/><title>Chapter 2</title></head>
  <body>
    <h1>Chapter 2: The Core Domain</h1>
    <p>The core domain contains the logic that makes the application
    unique. In BookWeaver, this means the <b>TextBatcher</b> and the
    <b>TranslationEngine</b> — components that know how to group text
    segments and orchestrate the translate-retry-save state machine.</p>
    <p>Crucially, the core domain knows <i>nothing</i> about the
    <code>%%</code> delimiter convention, the Gemini CLI subprocess,
    or EPUB ZIP structure. Those are adapter-level concerns.</p>
    <p>The <b>TranslationEngine</b> implements a split-retry resilience
    strategy: if a batch translation fails persistently, it splits the
    batch in half and retries each half recursively. This is pure domain
    logic — independent of any specific transport mechanism.</p>
    <p>By keeping the domain clean, we can write fast, deterministic
    unit tests that run in milliseconds, without any network access or
    external dependencies whatsoever.</p>
  </body>
</html>
"""


# ── Builder ───────────────────────────────────────────────────


def build_epub(output_path: Path) -> None:
    """Create a minimal, valid EPUB 3 file at *output_path*."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype MUST be first and MUST be uncompressed (ZIP_STORED)
        zf.writestr(
            zipfile.ZipInfo("mimetype"),
            _MIMETYPE.encode("ascii"),
        )
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", _CONTENT_OPF)
        zf.writestr("OEBPS/toc.ncx", _TOC_NCX)
        zf.writestr("OEBPS/nav.xhtml", _NAV_XHTML)
        zf.writestr("OEBPS/chapter1.xhtml", _CHAPTER1_XHTML)
        zf.writestr("OEBPS/chapter2.xhtml", _CHAPTER2_XHTML)

    output_path.write_bytes(buf.getvalue())
    print(f"Created: {output_path}")
    print(f"  Size:     {output_path.stat().st_size} bytes")
    print(f"  Chapters: 2  (chapter1.xhtml, chapter2.xhtml)")
    print(f"  Segments: ~8 translatable paragraphs")
    print(f"  Tags:     <b>, <i>, <code> present for format-retention test")


# ── Entry point ───────────────────────────────────────────────


if __name__ == "__main__":
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("test_book.epub")
    build_epub(output)
