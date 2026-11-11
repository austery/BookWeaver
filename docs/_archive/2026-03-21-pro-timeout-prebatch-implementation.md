# Pro Timeout Pre-Batching Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce Pro-model timeout waste in EPUB workflow by pre-splitting large chapter segment batches before the first model request.

**Architecture:** Add a deterministic batch planner in `ai/epub_translate_roundtrip.py` that enforces balanced limits (`<=18000` chars and `<=36` segments) for Pro requests, then keep existing recursive split-retry as a secondary safety net. Preserve ordering, checkpoint behavior, and fail-fast semantics.

**Tech Stack:** Python 3.14, pytest, BookWeaver EPUB workflow (`translatebook.sh` + `09_epub_translate_roundtrip.py` + `ai/epub_translate_roundtrip.py`)

---

### Task 1: Add failing tests for deterministic pre-batch planner

**Files:**
- Modify: `tests/unit/test_epub_translate_roundtrip.py`
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Write the failing test**

Add tests that define expected planner behavior and prove ordering + limit enforcement.

```python
def test_plan_segment_batches_enforces_balanced_limits() -> None:
    from ai.epub_translate_roundtrip import plan_segment_batches

    segments = [f"S{i}-" + ("x" * 500) for i in range(130)]
    batches = plan_segment_batches(
        segments,
        max_batch_chars=18_000,
        max_batch_segments=36,
    )

    assert [len(batch) for batch in batches] == [33, 36, 36, 25]
    assert all(1 <= len(batch) <= 36 for batch in batches)
    assert [item for batch in batches for item in batch] == segments


def test_plan_segment_batches_allows_oversized_single_segment() -> None:
    from ai.epub_translate_roundtrip import plan_segment_batches

    oversized = "y" * 30_000
    batches = plan_segment_batches(
        [oversized, "ok"],
        max_batch_chars=18_000,
        max_batch_segments=36,
    )

    assert len(batches) == 2
    assert batches[0] == [oversized]
    assert batches[1] == ["ok"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_plan_segment_batches_enforces_balanced_limits tests/unit/test_epub_translate_roundtrip.py::test_plan_segment_batches_allows_oversized_single_segment`

Expected: FAIL with import/name error because `plan_segment_batches` does not exist yet.

**Step 3: Write minimal implementation**

In `ai/epub_translate_roundtrip.py`, add planner function:

```python
def plan_segment_batches(
    segments: list[str],
    *,
    max_batch_chars: int,
    max_batch_segments: int,
) -> list[list[str]]:
    if max_batch_chars <= 0:
        raise ValueError("max_batch_chars must be > 0")
    if max_batch_segments <= 0:
        raise ValueError("max_batch_segments must be > 0")
    if not segments:
        return []

    planned: list[list[str]] = []
    current: list[str] = []
    current_chars = 0

    for segment in segments:
        separator_chars = len(_BATCH_SEPARATOR) if current else 0
        added_chars = len(segment) + separator_chars
        should_split = current and (
            len(current) >= max_batch_segments
            or current_chars + added_chars > max_batch_chars
        )
        if should_split:
            planned.append(current)
            current = [segment]
            current_chars = len(segment)
            continue

        current.append(segment)
        current_chars += added_chars

    if current:
        planned.append(current)
    return planned
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_plan_segment_batches_enforces_balanced_limits tests/unit/test_epub_translate_roundtrip.py::test_plan_segment_batches_allows_oversized_single_segment`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/unit/test_epub_translate_roundtrip.py ai/epub_translate_roundtrip.py
git commit -m "test: add failing specs for pro pre-batch planner"
```

---

### Task 2: Integrate planner into Pro chapter translation path

**Files:**
- Modify: `ai/epub_translate_roundtrip.py`
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Write the failing test**

Add integration tests that lock desired behavior:

```python
def test_translate_roundtrip_prebatches_pro_requests_before_retry() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-pro-prebatch.epub"
        output_epub = Path(temp_dir) / "translated-pro-prebatch.epub"
        paragraphs = [f"P{i}" for i in range(80)]
        _build_min_epub(source_epub, paragraphs=paragraphs)

        calls: list[str] = []

        def batch_translate(text: str) -> str:
            calls.append(text)
            return _translate_with_batch_separator(text)

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="pro",
            custom_prompt=None,
            translate_fn=batch_translate,
        )

        assert len(calls) > 1
        assert max(len(payload.split("\n\n%%\n\n")) for payload in calls) <= 36


def test_translate_roundtrip_flash_does_not_use_pro_prebatching() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-flash-no-prebatch.epub"
        output_epub = Path(temp_dir) / "translated-flash-no-prebatch.epub"
        paragraphs = [f"P{i}" for i in range(80)]
        _build_min_epub(source_epub, paragraphs=paragraphs)

        call_count = 0

        def batch_translate(text: str) -> str:
            nonlocal call_count
            call_count += 1
            return _translate_with_batch_separator(text)

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="flash",
            custom_prompt=None,
            translate_fn=batch_translate,
        )

        assert call_count == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_translate_roundtrip_prebatches_pro_requests_before_retry tests/unit/test_epub_translate_roundtrip.py::test_translate_roundtrip_flash_does_not_use_pro_prebatching`

Expected: FAIL because Pro currently still sends one large initial request.

**Step 3: Write minimal implementation**

In `ai/epub_translate_roundtrip.py`:

1. Add constants:

```python
_PRO_PREBATCH_MAX_CHARS = 18_000
_PRO_PREBATCH_MAX_SEGMENTS = 36
```

2. In `run_translate_roundtrip`, replace single-call chapter translation with planned iteration:

```python
segment_texts = [segment.text for segment in segments]
planned_batches: list[list[str]] = [segment_texts]
if resolved_model == "gemini-3-pro-preview":
    planned_batches = plan_segment_batches(
        segment_texts,
        max_batch_chars=_PRO_PREBATCH_MAX_CHARS,
        max_batch_segments=_PRO_PREBATCH_MAX_SEGMENTS,
    )

translations: list[str] = []
for batch in planned_batches:
    translated_batch = translate_segments_with_batch_retry(
        batch,
        translate_batch=batch_translate,
        context_label=doc_path,
    )
    translations.extend(translated_batch)
```

3. Keep checkpoint/integrity behavior unchanged.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_translate_roundtrip_prebatches_pro_requests_before_retry tests/unit/test_epub_translate_roundtrip.py::test_translate_roundtrip_flash_does_not_use_pro_prebatching`

Expected: PASS.

**Step 5: Commit**

```bash
git add ai/epub_translate_roundtrip.py tests/unit/test_epub_translate_roundtrip.py
git commit -m "feat: pre-batch pro epub segments before retry"
```

---

### Task 3: Add observability logs and regression protection

**Files:**
- Modify: `ai/epub_translate_roundtrip.py`
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Write the failing test**

Add a capsys-based log test to enforce observability contract:

```python
def test_translate_roundtrip_logs_planned_batch_summary_for_pro(capsys: pytest.CaptureFixture[str]) -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-log.epub"
        output_epub = Path(temp_dir) / "translated-log.epub"
        paragraphs = [f"P{i}" for i in range(80)]
        _build_min_epub(source_epub, paragraphs=paragraphs)

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="pro",
            custom_prompt=None,
            translate_fn=_translate_with_batch_separator,
        )

        stdout = capsys.readouterr().out
        assert "planned_batches=" in stdout
        assert "batch 1/" in stdout
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_translate_roundtrip_logs_planned_batch_summary_for_pro`

Expected: FAIL because planned batch logs are not emitted yet.

**Step 3: Write minimal implementation**

In `ai/epub_translate_roundtrip.py`, add logs after planning and before each planned batch call:

```python
print(
    f"[INFO] [{doc_index}/{len(spine_docs)}] Planned batches for {doc_path}: "
    f"planned_batches={len(planned_batches)}",
    flush=True,
)
for batch_index, batch in enumerate(planned_batches, start=1):
    batch_chars = len(join_segments_for_batch(batch))
    print(
        f"[INFO] [{doc_path}] Translating batch {batch_index}/{len(planned_batches)} "
        f"(segments={len(batch)}, chars={batch_chars})",
        flush=True,
    )
```

**Step 4: Run tests to verify all pass**

Run:

`uv run pytest -q tests/unit/test_epub_translate_roundtrip.py`

Expected: PASS for existing and new tests.

Then run full repo gate:

`uv run ruff check . && uv run ruff format --check . && uv run pytest -q && bash -n translatebook.sh`

Expected: all green.

**Step 5: Commit**

```bash
git add ai/epub_translate_roundtrip.py tests/unit/test_epub_translate_roundtrip.py
git commit -m "chore: add pro pre-batch observability logs"
```

---

### Task 4: Update contributor notes and verify CLI behavior

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Write the failing doc expectation (manual checklist)**

Add checklist item in commit message notes (not code test):

- Contributor notes must mention Pro pre-batch policy (`18k/36`) for EPUB workflow.

**Step 2: Verify current docs missing this detail**

Run: `python3 - <<'PY'\nfrom pathlib import Path\nprint('18k' in Path('CLAUDE.md').read_text(encoding='utf-8'))\nPY`

Expected: `False`.

**Step 3: Write minimal doc update**

Add one bullet under "Current behavior to remember":

- Pro model in EPUB workflow pre-batches large chapters with balanced limits (18000 chars / 36 segments per request) before recursive split-retry.

**Step 4: Verify docs and dry-run output**

Run:

`python3 - <<'PY'\nfrom pathlib import Path\nprint('18000 chars / 36 segments' in Path('CLAUDE.md').read_text(encoding='utf-8'))\nPY`

Expected: `True`.

Run CLI sanity:

`./translatebook.sh --dry-run --workflow epub --model pro '/path/to/book.epub'`

Expected: resolved workflow `epub`; command includes `09_epub_translate_roundtrip.py ... --model pro`.

**Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note pro pre-batch limits for epub workflow"
```

