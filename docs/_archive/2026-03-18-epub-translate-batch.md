# EPUB Translate Roundtrip Batch Prompt Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce Gemini call count in `--epub-translate-roundtrip` by switching from per-segment calls to batched chapter translation with strict `%%` alignment guarantees.

**Architecture:** Keep the existing package-aware roundtrip pipeline and strict integrity checks, but replace segment-by-segment translation with per-document batching. Use Immersive-style separator rules (`%%`), validate output count exactly, and add binary split retries when model output does not align.

**Tech Stack:** Python 3.13, `ai/gemini_provider.py`, `ai/epub_translate_roundtrip.py`, pytest, uv, shell orchestration in `translatebook.sh`

---

### Task 1: Add failing tests for batch prompt formatting and parsing

**Files:**
- Create: `tests/unit/test_epub_translate_batching.py`
- Test: `tests/unit/test_epub_translate_batching.py`

**Step 1: Write the failing test**

```python
def test_join_segments_uses_percent_delimiter():
    from ai.epub_translate_roundtrip import join_segments_for_batch
    assert join_segments_for_batch(["A", "B"]) == "A\n\n%%\n\nB"


def test_split_batch_translation_validates_count():
    from ai.epub_translate_roundtrip import split_batch_translation
    result = split_batch_translation("甲\n\n%%\n\n乙", expected_count=2)
    assert result == ["甲", "乙"]
```

```python
def test_split_batch_translation_raises_on_mismatch():
    from ai.epub_translate_roundtrip import split_batch_translation
    with pytest.raises(ValueError, match="count mismatch"):
        split_batch_translation("only-one", expected_count=2)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_batching.py -v`  
Expected: FAIL (functions missing).

**Step 3: Write minimal implementation**

No implementation in this task. Keep tests red.

**Step 4: Re-run to keep red baseline**

Run: `uv run pytest -q tests/unit/test_epub_translate_batching.py -v`  
Expected: FAIL.

**Step 5: Commit**

```bash
git add tests/unit/test_epub_translate_batching.py
git commit -m "test: add failing batch prompt parser tests for epub translate roundtrip"
```

### Task 2: Implement batch formatter/parser primitives

**Files:**
- Modify: `ai/epub_translate_roundtrip.py`
- Test: `tests/unit/test_epub_translate_batching.py`

**Step 1: Run failing tests**

Run: `uv run pytest -q tests/unit/test_epub_translate_batching.py -v`  
Expected: FAIL.

**Step 2: Write minimal implementation**

```python
def join_segments_for_batch(segments: list[str]) -> str:
    ...


def split_batch_translation(output_text: str, expected_count: int) -> list[str]:
    ...
```

Rules:
- Single segment input/output has no delimiter.
- Multi-segment uses `\n\n%%\n\n`.
- Output segment count must match expected count exactly.

**Step 3: Run tests to verify pass**

Run: `uv run pytest -q tests/unit/test_epub_translate_batching.py -v`  
Expected: PASS.

**Step 4: Run existing translate roundtrip tests**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add ai/epub_translate_roundtrip.py tests/unit/test_epub_translate_batching.py
git commit -m "feat: add batch segment formatter and parser for roundtrip translation"
```

### Task 3: Add failing tests for reduced call count and split retry

**Files:**
- Modify: `tests/unit/test_epub_translate_roundtrip.py`
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Write the failing test**

```python
def test_translate_roundtrip_uses_batch_call_per_doc():
    ...
    call_count = 0
    def batch_translate(text: str) -> str:
        nonlocal call_count
        call_count += 1
        return "..."
    run_translate_roundtrip(..., translate_fn=batch_translate)
    assert call_count == 1
```

```python
def test_translate_roundtrip_retries_with_split_on_batch_mismatch():
    ...
    def flaky_batch_translate(text: str) -> str:
        ...
    run_translate_roundtrip(..., translate_fn=flaky_batch_translate)
    assert retry_happened
```

**Step 2: Run test to verify fail**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -v`  
Expected: FAIL (current implementation calls per segment and has no split retry).

**Step 3: Write minimal implementation**

No implementation in this task. Keep tests red.

**Step 4: Re-run to keep red baseline**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -v`  
Expected: FAIL.

**Step 5: Commit**

```bash
git add tests/unit/test_epub_translate_roundtrip.py
git commit -m "test: add failing tests for batch call count and split retry"
```

### Task 4: Implement document-batch translation with binary split retry

**Files:**
- Modify: `ai/epub_translate_roundtrip.py`
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Run failing tests**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -v`  
Expected: FAIL.

**Step 2: Write minimal implementation**

Add:

```python
def translate_segments_with_batch_retry(...)->list[str]:
    # one batch request, parse, on mismatch recursively split and retry
    ...
```

Wire into `run_translate_roundtrip` so each doc calls batch translator instead of per-segment loop.

Prompt behavior for this mode:
- Use Immersive-style translation rules with `%%` separator contract.
- Keep existing `custom_prompt` appended when provided.

**Step 3: Run tests to verify pass**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py tests/unit/test_epub_translate_batching.py -v`  
Expected: PASS.

**Step 4: Run focused regression tests**

Run:

```bash
uv run pytest -q \
  tests/unit/test_epub_baseline_cli.py \
  tests/unit/test_epub_translate_patcher.py \
  tests/unit/test_epub_translate_roundtrip.py \
  tests/unit/test_epub_translate_batching.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add ai/epub_translate_roundtrip.py tests/unit/test_epub_translate_roundtrip.py tests/unit/test_epub_translate_batching.py
git commit -m "feat: batch epub roundtrip translation per document with split retry"
```

### Task 5: Docs update and full verification

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md`

**Step 1: Add docs checks**

Run: `rg -n "%%|batch|per-document|split retry|Immersive Translate 1.26.6" README.md docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md`  
Expected: missing some entries before update.

**Step 2: Update docs**

Add:
- New batching behavior (per-document request strategy)
- Why call count drops
- Mismatch handling (binary split retry)
- Keep note that model fallback is out of scope in this task

**Step 3: Re-run docs check**

Run: `rg -n "%%|batch|per-document|split retry|Immersive Translate 1.26.6" README.md docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md`  
Expected: matches present.

**Step 4: Full verification**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
bash -n translatebook.sh
uv run python -m py_compile 09_epub_translate_roundtrip.py ai/epub_translate_roundtrip.py ai/epub_package.py
```

Expected: all checks pass.

**Step 5: Commit**

```bash
git add README.md docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md
git commit -m "docs: document batch translation strategy for epub roundtrip mode"
```
