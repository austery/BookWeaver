# SPEC-012 Markdown Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the hexagonal architecture to support the Markdown translation workflow, achieving full format parity with the EPUB vertical slice and eliminating the split-brain state.

**Architecture:** The `MarkdownSourceAdapter` implements `IBookSource` by treating each `page*.md` file in a directory as one segment. After engine translation, `save()` delegates to the existing `BilingualMerger.merge()` for alternating bilingual output. The CLI routes by input format (auto-detected or explicit `--format`).

**Tech Stack:** Python 3.13, pytest, ruff, tach, existing `BilingualMerger`

**Worktree:** `.worktrees/hexagonal-engine` (branch `feature/spec012-hexagonal-engine`)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `ai/adapters/sources/markdown_adapter.py` | `MarkdownSourceAdapter` implementing `IBookSource` |
| Create | `tests/unit/test_adapter_markdown_source.py` | Unit tests for the adapter |
| Modify | `ai/cli.py` | Add format routing (epub/markdown), new args |
| Modify | `tests/unit/test_cli.py` | Tests for new CLI args and format routing |
| Create | `tests/fixtures/markdown_book/` | Tiny fixture dir with page*.md files for E2E |

---

### Task 1: MarkdownSourceAdapter — Failing Tests

**Files:**
- Create: `tests/unit/test_adapter_markdown_source.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for MarkdownSourceAdapter.

Tests segment extraction from page*.md files, translation application,
and bilingual merge output via save(). Uses temp directories — no real
translation calls.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ai.adapters.sources.markdown_adapter import MarkdownSourceAdapter
from ai.ports.source import TranslatedSegment


# ── Helpers ───────────────────────────────────────────────────


def _write_pages(tmp_path: Path, pages: dict[str, str]) -> Path:
    """Write page*.md files to tmp_path and return the directory."""
    for name, content in pages.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return tmp_path


# ── get_segments ──────────────────────────────────────────────


class TestGetSegments:
    def test_single_page(self, tmp_path: Path) -> None:
        _write_pages(tmp_path, {"page0001.md": "Hello world."})
        adapter = MarkdownSourceAdapter(tmp_path)

        segments = adapter.get_segments()

        assert len(segments) == 1
        assert segments[0].id == "page0001"
        assert segments[0].text == "Hello world."
        assert segments[0].metadata["filename"] == "page0001.md"

    def test_multiple_pages_sorted(self, tmp_path: Path) -> None:
        _write_pages(tmp_path, {
            "page0003.md": "Third",
            "page0001.md": "First",
            "page0002.md": "Second",
        })
        adapter = MarkdownSourceAdapter(tmp_path)

        segments = adapter.get_segments()

        assert [s.id for s in segments] == ["page0001", "page0002", "page0003"]
        assert [s.text for s in segments] == ["First", "Second", "Third"]

    def test_ignores_non_page_files(self, tmp_path: Path) -> None:
        _write_pages(tmp_path, {
            "page0001.md": "Keep",
            "output_page0001.md": "Ignore me",
            "config.txt": "Ignore me too",
        })
        adapter = MarkdownSourceAdapter(tmp_path)

        segments = adapter.get_segments()

        assert len(segments) == 1
        assert segments[0].text == "Keep"

    def test_empty_directory_returns_empty(self, tmp_path: Path) -> None:
        adapter = MarkdownSourceAdapter(tmp_path)

        segments = adapter.get_segments()

        assert segments == []


# ── apply_translations ────────────────────────────────────────


class TestApplyTranslations:
    def test_stores_translations(self, tmp_path: Path) -> None:
        _write_pages(tmp_path, {"page0001.md": "Hello"})
        adapter = MarkdownSourceAdapter(tmp_path)
        adapter.get_segments()

        adapter.apply_translations([
            TranslatedSegment(id="page0001", original="Hello", translated="你好"),
        ])

        # Translations are stored internally — verified via save()
        assert adapter._translations["page0001"] == "你好"

    def test_out_of_order_translations(self, tmp_path: Path) -> None:
        _write_pages(tmp_path, {
            "page0001.md": "First",
            "page0002.md": "Second",
        })
        adapter = MarkdownSourceAdapter(tmp_path)
        adapter.get_segments()

        adapter.apply_translations([
            TranslatedSegment(id="page0002", original="Second", translated="第二"),
            TranslatedSegment(id="page0001", original="First", translated="第一"),
        ])

        assert adapter._translations["page0001"] == "第一"
        assert adapter._translations["page0002"] == "第二"


# ── save (bilingual merge) ───────────────────────────────────


class TestSave:
    def test_produces_bilingual_markdown(self, tmp_path: Path) -> None:
        _write_pages(tmp_path, {
            "page0001.md": "Hello world.",
            "page0002.md": "Goodbye world.",
        })
        output_path = str(tmp_path / "output.md")

        adapter = MarkdownSourceAdapter(tmp_path)
        adapter.get_segments()
        adapter.apply_translations([
            TranslatedSegment(id="page0001", original="Hello world.", translated="你好世界。"),
            TranslatedSegment(id="page0002", original="Goodbye world.", translated="再见世界。"),
        ])
        adapter.save(output_path)

        output = Path(output_path).read_text(encoding="utf-8")
        assert "## Segment 1" in output
        assert "## Segment 2" in output
        assert "Hello world." in output
        assert "你好世界。" in output
        assert "Goodbye world." in output
        assert "再见世界。" in output
        assert "**中文译文**" in output

    def test_segments_ordered_by_page_number(self, tmp_path: Path) -> None:
        _write_pages(tmp_path, {
            "page0002.md": "Second page.",
            "page0001.md": "First page.",
        })
        output_path = str(tmp_path / "output.md")

        adapter = MarkdownSourceAdapter(tmp_path)
        adapter.get_segments()
        adapter.apply_translations([
            TranslatedSegment(id="page0001", original="First page.", translated="第一页。"),
            TranslatedSegment(id="page0002", original="Second page.", translated="第二页。"),
        ])
        adapter.save(output_path)

        output = Path(output_path).read_text(encoding="utf-8")
        # Segment 1 should be "First page" (page0001), not "Second page"
        seg1_pos = output.index("## Segment 1")
        seg2_pos = output.index("## Segment 2")
        first_pos = output.index("First page.")
        second_pos = output.index("Second page.")
        assert seg1_pos < first_pos < seg2_pos < second_pos
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/hexagonal-engine && uv run pytest tests/unit/test_adapter_markdown_source.py -v --tb=short`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai.adapters.sources.markdown_adapter'`

---

### Task 2: MarkdownSourceAdapter — Implementation

**Files:**
- Create: `ai/adapters/sources/markdown_adapter.py`

- [ ] **Step 3: Write the implementation**

```python
"""Markdown source adapter — wraps a directory of page*.md files.

Each ``page*.md`` file is treated as one translatable segment.
After translation, ``save()`` delegates to ``BilingualMerger.merge()``
for alternating bilingual output.

The engine sees only flat ``Segment`` objects — page file enumeration,
natural sorting, and bilingual formatting are handled internally.
"""

from __future__ import annotations

import re
from pathlib import Path

from ai.ports.source import IBookSource, Segment, TranslatedSegment

_PAGE_PATTERN = re.compile(r"^page\d+\.md$")


class MarkdownSourceAdapter(IBookSource):
    """Adapter for split-Markdown book directories.

    Args:
        markdown_dir: Directory containing ``page*.md`` files produced
            by the split step (``02_split_to_md.py``).
    """

    def __init__(self, markdown_dir: str | Path) -> None:
        self._dir = Path(markdown_dir)
        self._page_files: list[Path] = []
        self._translations: dict[str, str] = {}
        self._loaded = False

    def get_segments(self) -> list[Segment]:
        """Extract one segment per ``page*.md`` file, naturally sorted."""
        self._ensure_loaded()

        result: list[Segment] = []
        for page_path in self._page_files:
            text = page_path.read_text(encoding="utf-8")
            result.append(
                Segment(
                    id=page_path.stem,
                    text=text,
                    metadata={
                        "filename": page_path.name,
                        "path": str(page_path),
                    },
                )
            )
        return result

    def apply_translations(self, translated: list[TranslatedSegment]) -> None:
        """Store translations keyed by page ID."""
        for ts in translated:
            self._translations[ts.id] = ts.translated

    def save(self, output_path: str) -> None:
        """Merge originals + translations into bilingual Markdown."""
        from ai.bilingual_merger import BilingualMerger

        originals: list[str] = []
        translations: list[str] = []

        for page_path in self._page_files:
            originals.append(page_path.read_text(encoding="utf-8"))
            translations.append(self._translations.get(page_path.stem, ""))

        merged = BilingualMerger().merge(originals, translations)
        Path(output_path).write_text(merged, encoding="utf-8")

    # ── Internal ──────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._page_files = sorted(
            (p for p in self._dir.iterdir() if _PAGE_PATTERN.match(p.name)),
            key=_natural_sort_key,
        )
        self._loaded = True


def _natural_sort_key(path: Path) -> tuple[int, str]:
    """Sort ``page0001.md`` before ``page0002.md`` numerically."""
    digits = re.search(r"\d+", path.stem)
    return (int(digits.group()) if digits else 0, path.name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/hexagonal-engine && uv run pytest tests/unit/test_adapter_markdown_source.py -v --tb=short`
Expected: all 8 tests PASS

- [ ] **Step 5: Lint and tach check**

Run: `cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/hexagonal-engine && uv run ruff check ai/adapters/sources/markdown_adapter.py tests/unit/test_adapter_markdown_source.py && uv run tach check`
Expected: All checks passed, modules validated

- [ ] **Step 6: Commit**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/hexagonal-engine
git add ai/adapters/sources/markdown_adapter.py tests/unit/test_adapter_markdown_source.py
git commit -m "feat(adapters): add MarkdownSourceAdapter with 8 unit tests

Implements IBookSource for split-Markdown directories:
- get_segments(): one segment per page*.md, naturally sorted
- apply_translations(): stores by page ID
- save(): delegates to BilingualMerger.merge() for bilingual output

8 unit tests covering: sorting, non-page filtering, empty dir,
out-of-order translations, bilingual output format, segment ordering.

Part of SPEC-012: Markdown vertical slice

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: CLI Format Routing — Failing Tests

**Files:**
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 7: Add failing tests for format routing and new args**

Append to `tests/unit/test_cli.py`:

```python
class TestBuildParserFormatRouting:
    def test_input_format_default_is_auto(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["input.epub", "--output", "out.epub"])
        assert args.input_format == "auto"

    def test_input_format_markdown(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "input.md", "--output", "out.md", "--input-format", "markdown",
            "--markdown-dir", "/tmp/pages"
        ])
        assert args.input_format == "markdown"
        assert args.markdown_dir == "/tmp/pages"

    def test_input_format_epub(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "input.epub", "--output", "out.epub", "--input-format", "epub"
        ])
        assert args.input_format == "epub"


class TestDetectInputFormat:
    def test_epub_extension(self) -> None:
        assert detect_input_format("book.epub") == "epub"

    def test_md_extension(self) -> None:
        assert detect_input_format("page.md") == "markdown"

    def test_unknown_defaults_to_epub(self) -> None:
        assert detect_input_format("book.pdf") == "epub"
```

Update import at the top of the test file:

```python
from ai.cli import build_parser, build_system_prompt, _get_language_name, detect_input_format
```

- [ ] **Step 8: Run tests to verify they fail**

Run: `cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/hexagonal-engine && uv run pytest tests/unit/test_cli.py -v --tb=short`
Expected: FAIL (new tests fail on missing `detect_input_format` and missing `--input-format` arg)

---

### Task 4: CLI Format Routing — Implementation

**Files:**
- Modify: `ai/cli.py`

- [ ] **Step 9: Add `detect_input_format()` and new CLI args**

Add the detection function (near the top helpers section):

```python
def detect_input_format(input_path: str) -> str:
    """Auto-detect input format from file extension."""
    ext = Path(input_path).suffix.lower()
    if ext == ".epub":
        return "epub"
    if ext == ".md":
        return "markdown"
    return "epub"  # default for unknown extensions (PDF, DOCX go through Calibre)
```

Add new arguments to `build_parser()`:

```python
    p.add_argument(
        "--input-format",
        choices=["auto", "epub", "markdown"],
        default="auto",
        help="Input format (default: auto-detect from extension)",
    )
    p.add_argument(
        "--markdown-dir",
        default=None,
        help="Directory with page*.md files (for markdown format)",
    )
```

Update `run()` to add format routing:

```python
def run(
    *,
    input_path: str,          # renamed from input_epub
    output: str,
    input_format: str = "auto",
    markdown_dir: str | None = None,
    # ... all other existing kwargs unchanged ...
) -> None:
    # ... existing config/model/provider/prompt setup unchanged ...

    # 5. Create source adapter (format routing)
    fmt = input_format if input_format != "auto" else detect_input_format(input_path)
    if fmt == "epub":
        source = EpubSourceAdapter(input_path)
    elif fmt == "markdown":
        md_dir = markdown_dir or str(Path(input_path).parent)
        source = MarkdownSourceAdapter(md_dir)
    else:
        raise ValueError(f"Unsupported format: {fmt}")

    # 6. Execute (unchanged)
    ...
```

Add the import at the top of `ai/cli.py`:

```python
from ai.adapters.sources.markdown_adapter import MarkdownSourceAdapter
```

Update `main()` to pass the new args:

```python
def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    run(
        input_path=args.input_epub,  # positional arg still named input_epub for compat
        output=args.output,
        # ... existing args ...
        input_format=args.input_format,
        markdown_dir=args.markdown_dir,
    )
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/hexagonal-engine && uv run pytest tests/unit/test_cli.py -v --tb=short`
Expected: all 16 tests PASS (10 existing + 6 new)

- [ ] **Step 11: Lint and tach check**

Run: `cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/hexagonal-engine && uv run ruff check ai/cli.py tests/unit/test_cli.py && uv run tach check`
Expected: All checks passed

- [ ] **Step 12: Commit**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/hexagonal-engine
git add ai/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add Markdown format routing and auto-detection

- detect_input_format() resolves epub/markdown from file extension
- --input-format flag (auto/epub/markdown) with auto as default
- --markdown-dir flag for split-page directories
- run() routes to EpubSourceAdapter or MarkdownSourceAdapter
- 6 new tests for format detection and CLI args

Part of SPEC-012: Markdown vertical slice

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: E2E Dual-Targeting Test

**Files:**
- Create: `tests/fixtures/markdown_book/page0001.md`
- Create: `tests/fixtures/markdown_book/page0002.md`

- [ ] **Step 13: Create markdown test fixture**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/hexagonal-engine
mkdir -p tests/fixtures/markdown_book
```

Write `tests/fixtures/markdown_book/page0001.md`:
```markdown
# Ports and Adapters

The hexagonal architecture isolates application core from external concerns. A **port** defines an interface that the core expects to be satisfied.

An *adapter* is the concrete implementation that connects an external technology to the port interface.
```

Write `tests/fixtures/markdown_book/page0002.md`:
```markdown
# The Core Domain

The core domain contains the **TextBatcher** and the **TranslationEngine** — components that know how to group text segments and orchestrate translation.

The core knows *nothing* about the `%%` delimiter convention or EPUB ZIP structure. Those are adapter-level concerns.
```

- [ ] **Step 14: Run old pipeline (03_translate_md.py) on fixture**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/hexagonal-engine
mkdir -p tmp/e2e_md
cp tests/fixtures/markdown_book/page*.md tmp/e2e_md/
uv run python 03_translate_md.py --temp-dir tmp/e2e_md --output-lang zh --model gemini-2.5-flash
```

Then merge:
```bash
uv run python 04_merge_md.py --temp-dir tmp/e2e_md
```

Output: `tmp/e2e_md/output.md`

- [ ] **Step 15: Run new CLI on same fixture**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/hexagonal-engine
uv run python -m ai.cli dummy.md \
  --output tmp/e2e_md/new_output.md \
  --output-lang zh \
  --model gemini-2.5-flash \
  --provider cli \
  --input-format markdown \
  --markdown-dir tests/fixtures/markdown_book
```

Output: `tmp/e2e_md/new_output.md`

- [ ] **Step 16: Compare outputs structurally**

Verify both outputs:
- Contain `## Segment 1` and `## Segment 2`
- Contain `**中文译文**` markers
- Contain Chinese translations
- Contain the original English text
- Same segment count

- [ ] **Step 17: Run full test suite for parity**

Run: `cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/hexagonal-engine && uv run pytest -q -x --tb=short -p no:tach`
Expected: 310+ passed (original 310 + new markdown tests), 0 failures

- [ ] **Step 18: Commit E2E results**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/hexagonal-engine
git add tests/fixtures/markdown_book/ .gitignore
git commit -m "test(e2e): Markdown dual-targeting parity confirmed

Both pipelines on 2-page markdown fixture:
- old: 03_translate_md.py + 04_merge_md.py
- new: python -m ai.cli --input-format markdown

Structural parity: same segment count, bilingual markers, Chinese output.

Part of SPEC-012: Markdown vertical slice complete

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Verification Checklist

After all tasks:
- [ ] `uv run ruff check .` passes
- [ ] `uv run tach check` passes (all modules validated)
- [ ] `uv run pytest -q` — 318+ passed, 0 failed
- [ ] Both EPUB and Markdown E2E dual-targeting confirmed
- [ ] No legacy scripts broken (03, 04, 09 all still functional)
