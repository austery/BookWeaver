# EPUB Block Anchor Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor EPUB translate roundtrip anchoring from inline text slots to block-level segments so bilingual output remains readable and avoids inline-tag injection.

**Architecture:** Keep existing package-aware translate roundtrip pipeline, batch translation, and integrity checks. Replace extraction and patching internals in `ai/epub_package.py` with block-level segment metadata and block-level translation insertion. Validate with targeted unit tests plus sampled multi-book chapter checks.

**Tech Stack:** Python 3.13, `xml.etree.ElementTree`, pytest, uv, shell orchestration in `translatebook.sh`

---

### Task 1: Add failing tests for block-level extraction contract

**Files:**
- Modify: `tests/unit/test_epub_translate_patcher.py`
- Test: `tests/unit/test_epub_translate_patcher.py`

**Step 1: Write the failing test**

```python
def test_extract_translatable_segments_returns_block_level_segments() -> None:
    from ai.epub_package import extract_translatable_segments

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<p>Hello <a href='x'>link</a> world.</p>"
        "<p>Second paragraph.</p>"
        "</body></html>"
    )
    segments = extract_translatable_segments(source)
    assert len(segments) == 2
    assert segments[0].text == "Hello link world."
    assert segments[1].text == "Second paragraph."
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_patcher.py::test_extract_translatable_segments_returns_block_level_segments`
Expected: FAIL (current extractor returns slot-level segments).

**Step 3: Keep implementation unchanged**

No production code changes in this task.

**Step 4: Re-run to keep red baseline**

Run: `uv run pytest -q tests/unit/test_epub_translate_patcher.py::test_extract_translatable_segments_returns_block_level_segments`
Expected: FAIL.

**Step 5: Commit**

```bash
git add tests/unit/test_epub_translate_patcher.py
git commit -m "test: add failing block-level extraction contract for epub roundtrip"
```

### Task 2: Add failing tests for block-level patching safety

**Files:**
- Modify: `tests/unit/test_epub_translate_patcher.py`
- Test: `tests/unit/test_epub_translate_patcher.py`

**Step 1: Write the failing tests**

```python
def test_patch_xhtml_alternating_inserts_one_translation_block_per_source_block() -> None:
    from ai.epub_package import patch_xhtml_alternating

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<p>Alpha <a href='u'>Link</a> tail.</p>"
        "</body></html>"
    )
    patched = patch_xhtml_alternating(source, ["阿尔法链接尾部。"])
    assert patched.count('class="bw-translation"') == 1


def test_patch_xhtml_alternating_never_injects_translation_inside_anchor() -> None:
    from ai.epub_package import patch_xhtml_alternating

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<p>Read <a href='https://example.com'>docs</a> now.</p>"
        "</body></html>"
    )
    patched = patch_xhtml_alternating(source, ["现在阅读文档。"])
    assert '<a href="https://example.com">docs' in patched
    assert '<a href="https://example.com"><span class="bw-translation"' not in patched
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/unit/test_epub_translate_patcher.py -k "one_translation_block or never_injects_translation_inside_anchor"`
Expected: FAIL.

**Step 3: Keep implementation unchanged**

No production code changes in this task.

**Step 4: Re-run to preserve red baseline**

Run: same command as Step 2.
Expected: FAIL.

**Step 5: Commit**

```bash
git add tests/unit/test_epub_translate_patcher.py
git commit -m "test: add failing block patching safety tests for anchor handling"
```

### Task 3: Implement block-level extractor in epub package

**Files:**
- Modify: `ai/epub_package.py`
- Test: `tests/unit/test_epub_translate_patcher.py`

**Step 1: Run failing tests**

Run: `uv run pytest -q tests/unit/test_epub_translate_patcher.py`
Expected: FAIL from new block-level extraction tests.

**Step 2: Write minimal implementation**

Implement in `ai/epub_package.py`:

- Update `TranslatableSegment` to include block locator metadata (e.g. path/index).
- Add block candidate detection for tags: `p`, `li`, `blockquote`, `td`, `th`, `dd`.
- Exclude heading and TOC behavior as currently defined.
- Extract one text payload per block using ordered text flattening (`itertext`) within block.

**Step 3: Run extractor-focused tests**

Run: `uv run pytest -q tests/unit/test_epub_translate_patcher.py -k "extract_translatable_segments"`
Expected: PASS.

**Step 4: Run full patcher suite**

Run: `uv run pytest -q tests/unit/test_epub_translate_patcher.py`
Expected: partial FAIL or PASS depending on patcher alignment.

**Step 5: Commit**

```bash
git add ai/epub_package.py tests/unit/test_epub_translate_patcher.py
git commit -m "feat: implement block-level segment extraction for epub roundtrip"
```

### Task 4: Implement block-level patcher insertion and anchor-safe rendering

**Files:**
- Modify: `ai/epub_package.py`
- Modify: `ai/epub_translate_roundtrip.py`
- Test: `tests/unit/test_epub_translate_patcher.py`
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Run failing patcher tests**

Run: `uv run pytest -q tests/unit/test_epub_translate_patcher.py`
Expected: FAIL in anchor-safe/block insertion tests.

**Step 2: Write minimal implementation**

In `ai/epub_package.py`:

- Patch by block locator (not text/tail slots).
- Insert one sibling translation block after each source block.
- Use context-safe fallback tag when parent cannot contain `<p>` (e.g. in list/table contexts).
- Keep class name `bw-translation`.
- Ensure translation is never appended inside inline tags.

In `ai/epub_translate_roundtrip.py`:

- Update consumption of segment metadata if needed.
- Keep batch and retry behavior unchanged.

**Step 3: Run patcher and roundtrip tests**

Run:

```bash
uv run pytest -q \
  tests/unit/test_epub_translate_patcher.py \
  tests/unit/test_epub_translate_roundtrip.py
```

Expected: PASS.

**Step 4: Run targeted regression for checkpoint/resume**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_translate_roundtrip_resume_skips_completed_docs`
Expected: PASS.

**Step 5: Commit**

```bash
git add ai/epub_package.py ai/epub_translate_roundtrip.py tests/unit/test_epub_translate_patcher.py tests/unit/test_epub_translate_roundtrip.py
git commit -m "feat: patch epub translations at block anchors with inline-safe insertion"
```

### Task 5: Add multi-book sampling verification script and document procedure

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture/specs/SPEC-008-epub-block-anchor-redesign.md`

**Step 1: Add reproducible sampling command notes**

Add to README:

- how to sample 3 body chapters per book in `tmp/`;
- metrics to inspect:
  - anchor-embedded-translation count
  - multi-translation paragraph ratio.

**Step 2: Update SPEC-008 validation section**

Add explicit sampled corpus procedure and pass criteria.

**Step 3: Verify docs mention new behavior**

Run: `rg -n "block-level|anchor|bw-translation|sampling|inline" README.md docs/architecture/specs/SPEC-008-epub-block-anchor-redesign.md`
Expected: relevant matches present.

**Step 4: Commit**

```bash
git add README.md docs/architecture/specs/SPEC-008-epub-block-anchor-redesign.md
git commit -m "docs: add block-anchor validation workflow for epub roundtrip"
```

### Task 6: Full verification and final cleanup

**Files:**
- Modify (if needed): `ai/epub_package.py`, `ai/epub_translate_roundtrip.py`, related tests/docs

**Step 1: Run quality gates**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
bash -n translatebook.sh
uv run python -m py_compile 09_epub_translate_roundtrip.py ai/epub_translate_roundtrip.py ai/epub_package.py
```

Expected: all PASS.

**Step 2: Manual spot check on 2-3 sampled passages**

- Rebuild one translated EPUB sample and inspect known problematic paragraphs.
- Verify no translation appears inside `<a>`.

**Step 3: Commit final polish if needed**

```bash
git add -A
git commit -m "chore: finalize block-anchor redesign verification"
```

