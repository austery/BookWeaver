# EPUB Roundtrip Baseline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a strict EPUB baseline mode that roundtrips source EPUBs with zero text mutation while preserving cover, clickable TOC/navigation, and package structure.

**Architecture:** Implement a repack-first workflow that parses OPF/NCX/NAV and validates link/resource integrity before and after repack. Keep baseline mode separate from translation rendering so we can compare source vs rebuilt EPUB behavior directly. Reuse these package-aware utilities later for translation-safe patching.

**Tech Stack:** Python 3.13, zipfile, xml.etree.ElementTree, lxml/BeautifulSoup (optional parser fallback), pytest, uv, shell integration in `translatebook.sh`

---

### Task 1: Add failing baseline CLI contract tests

**Files:**
- Create: `tests/unit/test_epub_baseline_cli.py`
- Test: `tests/unit/test_epub_baseline_cli.py`

**Step 1: Write the failing test**

```python
from __future__ import annotations

from pathlib import Path


def test_translatebook_help_includes_epub_baseline_mode():
    content = Path("translatebook.sh").read_text(encoding="utf-8")
    assert "--epub-baseline" in content


def test_roundtrip_script_exists():
    assert Path("08_epub_roundtrip_baseline.py").exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_baseline_cli.py -v`  
Expected: FAIL (`--epub-baseline` missing and script missing).

**Step 3: Write minimal implementation**

No implementation in this task. Keep tests red.

**Step 4: Re-run to keep red baseline**

Run: `uv run pytest -q tests/unit/test_epub_baseline_cli.py -v`  
Expected: FAIL.

**Step 5: Commit**

```bash
git add tests/unit/test_epub_baseline_cli.py
git commit -m "test: add failing epub baseline cli contract checks"
```

### Task 2: Add failing EPUB package model tests

**Files:**
- Create: `tests/unit/test_epub_package_model.py`
- Test: `tests/unit/test_epub_package_model.py`

**Step 1: Write the failing test**

```python
from __future__ import annotations

from pathlib import Path
import tempfile
import zipfile


def _build_min_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""")
        z.writestr("content.opf", """<?xml version="1.0"?>
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
  <guide><reference type="cover" title="Cover" href="chapter1.xhtml"/></guide>
</package>""")
        z.writestr("chapter1.xhtml", "<html xmlns='http://www.w3.org/1999/xhtml'><body><h1 id='c1'>Chapter</h1></body></html>")
        z.writestr("toc.ncx", "<ncx></ncx>")
        z.writestr("cover.jpg", "x")


def test_load_epub_package_extracts_cover_and_spine():
    from ai.epub_package import load_epub_package

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "book.epub"
        _build_min_epub(p)
        model = load_epub_package(p)
        assert model.opf_path == "content.opf"
        assert model.cover_item_id == "cover-image"
        assert model.spine_itemrefs == ["c1"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_package_model.py -v`  
Expected: FAIL (`ai.epub_package` missing).

**Step 3: Write minimal implementation**

No implementation in this task. Keep tests red.

**Step 4: Re-run to keep red baseline**

Run: `uv run pytest -q tests/unit/test_epub_package_model.py -v`  
Expected: FAIL.

**Step 5: Commit**

```bash
git add tests/unit/test_epub_package_model.py
git commit -m "test: add failing epub package model tests"
```

### Task 3: Implement EPUB package parser and roundtrip repacker

**Files:**
- Create: `ai/epub_package.py`
- Create: `08_epub_roundtrip_baseline.py`
- Test: `tests/unit/test_epub_package_model.py`

**Step 1: Run failing tests**

Run: `uv run pytest -q tests/unit/test_epub_package_model.py -v`  
Expected: FAIL.

**Step 2: Write minimal implementation**

```python
# ai/epub_package.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import zipfile
import xml.etree.ElementTree as ET


@dataclass
class EpubPackageModel:
    epub_path: Path
    opf_path: str
    cover_item_id: str | None
    spine_itemrefs: list[str]


def load_epub_package(epub_path: Path) -> EpubPackageModel:
    # parse container.xml -> OPF -> metadata/manifest/spine
    ...


def repack_epub(source_epub: Path, output_epub: Path) -> None:
    # extract and repack without content mutation
    ...
```

```python
# 08_epub_roundtrip_baseline.py
from __future__ import annotations

import argparse
from pathlib import Path
from ai.epub_package import load_epub_package, repack_epub


def main() -> None:
    parser = argparse.ArgumentParser(description="Roundtrip EPUB baseline mode")
    parser.add_argument("input_epub")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    src = Path(args.input_epub).expanduser().resolve()
    dst = Path(args.output).expanduser().resolve()
    model = load_epub_package(src)
    print(f"OPF: {model.opf_path}, cover: {model.cover_item_id}, spine: {len(model.spine_itemrefs)} items")
    repack_epub(src, dst)
    print(f"Roundtrip EPUB generated: {dst}")
```

**Step 3: Run tests to verify pass**

Run: `uv run pytest -q tests/unit/test_epub_package_model.py -v`  
Expected: PASS.

**Step 4: Add smoke run**

Run: `uv run python 08_epub_roundtrip_baseline.py tmp/Psycho-Cybernetics.epub --output tmp/Psycho-Cybernetics.roundtrip.epub`  
Expected: output EPUB created, parser summary printed.

**Step 5: Commit**

```bash
git add ai/epub_package.py 08_epub_roundtrip_baseline.py tests/unit/test_epub_package_model.py
git commit -m "feat: add epub package parser and baseline roundtrip script"
```

### Task 4: Add failing link/asset integrity tests

**Files:**
- Create: `tests/unit/test_epub_integrity_checks.py`
- Modify: `ai/epub_package.py`
- Test: `tests/unit/test_epub_integrity_checks.py`

**Step 1: Write the failing test**

```python
from __future__ import annotations

from pathlib import Path


def test_detects_broken_fragment_links_in_spine_docs():
    from ai.epub_package import validate_fragment_links

    html = "<html><body><a href='#missing'>go</a><h1 id='ok'>ok</h1></body></html>"
    report = validate_fragment_links({"chapter1.xhtml": html})
    assert report.broken_count == 1


def test_detects_missing_manifest_assets():
    from ai.epub_package import validate_manifest_assets

    manifest = ["images/a.jpg", "styles/main.css"]
    existing = {"styles/main.css"}
    report = validate_manifest_assets(manifest, existing)
    assert "images/a.jpg" in report.missing_paths
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_integrity_checks.py -v`  
Expected: FAIL (validators missing).

**Step 3: Write minimal implementation**

```python
def validate_fragment_links(docs: dict[str, str]) -> LinkReport:
    # parse ids and href="#..."
    ...


def validate_manifest_assets(manifest_paths: list[str], existing_paths: set[str]) -> AssetReport:
    ...
```

**Step 4: Re-run tests**

Run: `uv run pytest -q tests/unit/test_epub_integrity_checks.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/unit/test_epub_integrity_checks.py ai/epub_package.py
git commit -m "feat: add epub link and asset integrity validators"
```

### Task 5: Wire baseline mode into translatebook orchestrator

**Files:**
- Modify: `translatebook.sh`
- Test: `tests/unit/test_translatebook_temp_dir.py`
- Test: `tests/unit/test_epub_baseline_cli.py`

**Step 1: Add failing test for flag wiring**

```python
def test_translatebook_has_epub_baseline_flag():
    from pathlib import Path
    content = Path("translatebook.sh").read_text(encoding="utf-8")
    assert "--epub-baseline" in content
    assert "08_epub_roundtrip_baseline.py" in content
```

**Step 2: Run tests to verify fail**

Run: `uv run pytest -q tests/unit/test_epub_baseline_cli.py -v`  
Expected: FAIL before wiring.

**Step 3: Implement minimal shell wiring**

```bash
# parse_args:
--epub-baseline) EPUB_BASELINE=true ;;

# main:
if [[ "$EPUB_BASELINE" == true ]]; then
  python3 "${SCRIPT_DIR}/08_epub_roundtrip_baseline.py" "$INPUT_FILE" --output "${base_temp_dir}/baseline_roundtrip.epub"
  exit 0
fi
```

**Step 4: Re-run tests**

Run: `uv run pytest -q tests/unit/test_epub_baseline_cli.py tests/unit/test_translatebook_temp_dir.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add translatebook.sh tests/unit/test_epub_baseline_cli.py tests/unit/test_translatebook_temp_dir.py
git commit -m "feat: add epub baseline mode entry in orchestrator"
```

### Task 6: Add docs and verification workflow for baseline mode

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Create: `docs/architecture/specs/SPEC-005-epub-roundtrip-baseline.md`

**Step 1: Add docs checklist (failing state)**

Run: `rg -n "epub-baseline|baseline_roundtrip|SPEC-005" README.md CLAUDE.md docs/architecture/specs`  
Expected: Missing entries.

**Step 2: Write minimal documentation**

Include:
- command examples for baseline mode
- acceptance checklist (cover/TOC/clickability/integrity)
- known limitations and reader-compatibility notes

**Step 3: Re-run docs check**

Run: `rg -n "epub-baseline|baseline_roundtrip|SPEC-005" README.md CLAUDE.md docs/architecture/specs`  
Expected: Matches in all three files.

**Step 4: Full verification**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
bash -n translatebook.sh
uv run python -m py_compile 08_epub_roundtrip_baseline.py ai/epub_package.py
```

Expected: all checks pass.

**Step 5: Commit**

```bash
git add README.md CLAUDE.md docs/architecture/specs/SPEC-005-epub-roundtrip-baseline.md
git commit -m "docs: add epub baseline mode specification and usage guide"
```

