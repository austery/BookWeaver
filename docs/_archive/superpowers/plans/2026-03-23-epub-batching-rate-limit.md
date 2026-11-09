# EPUB Batching & Rate-Limit Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix Pro model EPUB translation to use char-only batching (eliminating 23-call bursts), catch 429 rate-limit errors with backoff retry, and apply a longer timeout for larger Pro batches.

**Architecture:** Three focused commits: (1) add `RateLimitError` + `_parse_retry_after` to `gemini_provider.py`; (2) remove segment-count limit from `plan_segment_batches` and raise char limit to 60K; (3) wire rate-limit backoff retry and Pro timeout into `translate_segments_with_batch_retry` and `batch_translate`. Each commit is independently testable.

**Tech Stack:** Python, pytest, `uv run ruff check/format`, `subprocess` monkeypatching

---

## File Map

| File | Role in this change |
|------|---------------------|
| `ai/gemini_provider.py` | Add `RateLimitError` exception class + `_parse_retry_after` helper; update `translate_chunk` error branch |
| `ai/epub_translate_roundtrip.py` | Remove `_PRO_PREBATCH_MAX_SEGMENTS`; raise `_PRO_PREBATCH_MAX_CHARS` 18K→60K; add `_PRO_TIMEOUT_SECONDS=300` + `_RATE_LIMIT_BACKOFF_SECONDS=[60,120]`; update `plan_segment_batches`; update `translate_segments_with_batch_retry`; update `batch_translate` closure |
| `tests/unit/test_gemini_provider.py` | Add 6 new tests for `RateLimitError` and `_parse_retry_after` |
| `tests/unit/test_epub_translate_roundtrip.py` | Update 2 existing tests (remove `max_batch_segments`); add 7 new tests |

---

## Task 1: RateLimitError + _parse_retry_after in gemini_provider.py

**Files:**
- Modify: `ai/gemini_provider.py`
- Test: `tests/unit/test_gemini_provider.py`

### Background

Currently `translate_chunk` raises `RuntimeError` for all non-zero return codes, including 429. The retry logic in `epub_translate_roundtrip.py` cannot distinguish rate-limit errors from permanent failures. This task adds a dedicated `RateLimitError` subclass and the detection logic.

---

- [ ] **Step 1: Write 8 failing tests**

Add to `tests/unit/test_gemini_provider.py`:

```python
def test_rate_limit_error_raised_on_resource_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai.gemini_provider import GeminiProvider, RateLimitError

    provider = GeminiProvider(model="gemini-3-pro-preview")

    def mock_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["gemini"], returncode=1, stdout="",
            stderr='{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}'
        )

    monkeypatch.setattr(subprocess, "run", mock_run)
    with pytest.raises(RateLimitError):
        provider.translate_chunk(text="hello", chunk_size=5, system_prompt="translate")


def test_rate_limit_error_is_subclass_of_runtime_error() -> None:
    from ai.gemini_provider import RateLimitError
    assert issubclass(RateLimitError, RuntimeError)


def test_rate_limit_error_stores_retry_after() -> None:
    from ai.gemini_provider import RateLimitError
    err = RateLimitError("rate limited", retry_after_seconds=45)
    assert err.retry_after_seconds == 45


def test_rate_limit_error_retry_after_defaults_to_none() -> None:
    from ai.gemini_provider import RateLimitError
    err = RateLimitError("rate limited")
    assert err.retry_after_seconds is None


def test_non_rate_limit_failure_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai.gemini_provider import GeminiProvider, RateLimitError

    provider = GeminiProvider(model="gemini-3-pro-preview")

    def mock_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["gemini"], returncode=1, stdout="", stderr="model not found"
        )

    monkeypatch.setattr(subprocess, "run", mock_run)
    with pytest.raises(RuntimeError) as exc_info:
        provider.translate_chunk(text="hello", chunk_size=5, system_prompt="translate")
    assert not isinstance(exc_info.value, RateLimitError)


def test_parse_retry_after_json_format() -> None:
    from ai.gemini_provider import _parse_retry_after
    assert _parse_retry_after('"retryDelay": "45s"') == 45


def test_parse_retry_after_natural_language() -> None:
    from ai.gemini_provider import _parse_retry_after
    assert _parse_retry_after("Please retry after 30 seconds.") == 30


def test_parse_retry_after_returns_none_when_absent() -> None:
    from ai.gemini_provider import _parse_retry_after
    assert _parse_retry_after("RESOURCE_EXHAUSTED: quota exceeded") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_gemini_provider.py -v 2>&1 | tail -20
```

Expected: `ImportError: cannot import name 'RateLimitError'` or `AttributeError: module has no attribute '_parse_retry_after'`

- [ ] **Step 3: Implement RateLimitError, _parse_retry_after, and update translate_chunk**

Replace the full content of `ai/gemini_provider.py` with:

```python
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


class RateLimitError(RuntimeError):
    """Raised when Gemini CLI returns 429 / RESOURCE_EXHAUSTED."""

    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def _parse_retry_after(stderr: str) -> int | None:
    """Extract retry delay seconds from Gemini CLI stderr.

    Tries JSON format first (``"retryDelay": "30s"``), then natural-language
    format (``"retry after 30 seconds"``). Returns ``None`` if neither is found.
    """
    m = re.search(r'"retryDelay":\s*"(\d+)s"', stderr)
    if m:
        return int(m.group(1))
    m = re.search(r"retry after (\d+)", stderr, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


@dataclass(slots=True)
class GeminiProvider:
    model: str

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("Gemini model must be a non-empty string")

    def translate_chunk(
        self,
        text: str,
        chunk_size: int,
        system_prompt: str,
        timeout_seconds: int = 180,
    ) -> str:
        # chunk_size is reserved for future rate-limiting; it is not used
        # functionally in the current implementation.
        if chunk_size < 0:
            raise ValueError("chunk_size must be >= 0")
        if not text.strip():
            return ""

        prompt = f"{system_prompt}\n\n{text}"
        result = subprocess.run(
            ["gemini", "--model", self.model],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            if "429" in stderr or "RESOURCE_EXHAUSTED" in stderr:
                wait = _parse_retry_after(stderr)
                raise RateLimitError(f"Gemini rate limited: {stderr}", retry_after_seconds=wait)
            raise RuntimeError(f"Gemini CLI failed: {stderr}")

        return (result.stdout or "").strip()
```

- [ ] **Step 4: Run all tests**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```

Expected: all tests pass, 0 ruff errors

- [ ] **Step 5: Commit**

```bash
git add ai/gemini_provider.py tests/unit/test_gemini_provider.py
git commit -m "feat: add RateLimitError and _parse_retry_after to gemini_provider"
```

---

## Task 2: Char-Only Batching (remove max_batch_segments, raise char limit to 60K)

**Files:**
- Modify: `ai/epub_translate_roundtrip.py` (lines 36–37, 326–361, 578–582)
- Test: `tests/unit/test_epub_translate_roundtrip.py` (lines 158–185)

### Background

`plan_segment_batches` currently accepts two limits: `max_batch_chars` and `max_batch_segments`. For pages with many short segments, the segment limit triggers first, creating excessive API calls (23 for `index.xhtml`). This task removes the segment limit entirely and raises the char limit from 18K to 60K.

Two existing tests pass `max_batch_segments=36` — these will break after the signature change and must be updated in this task.

---

- [ ] **Step 1: Update the two existing tests (they are currently GREEN; this makes them RED)**

In `tests/unit/test_epub_translate_roundtrip.py`, replace lines 158–185:

```python
def test_plan_segment_batches_enforces_char_limit_and_order() -> None:
    from ai.epub_translate_roundtrip import plan_segment_batches

    # Each segment is ~500 chars; 60K limit → batches of ~120 segments
    segments = [f"S{i}-" + ("x" * 500) for i in range(130)]
    batches = plan_segment_batches(
        segments,
        max_batch_chars=60_000,
    )

    # All segments preserved in order
    assert [item for batch in batches for item in batch] == segments
    # No batch exceeds char limit (except a single oversized segment)
    sep_len = len("\n\n%%\n\n")
    for batch in batches:
        joined_len = sum(len(s) for s in batch) + sep_len * (len(batch) - 1)
        assert joined_len <= 60_000 or len(batch) == 1


def test_plan_segment_batches_allows_single_oversized_segment() -> None:
    from ai.epub_translate_roundtrip import plan_segment_batches

    oversized = "y" * 30_000
    batches = plan_segment_batches(
        [oversized, "ok"],
        max_batch_chars=18_000,
    )

    assert len(batches) == 2
    assert batches[0] == [oversized]
    assert batches[1] == ["ok"]
```

- [ ] **Step 2: Add 2 new tests (also RED until implementation)**

```python
def test_plan_segment_batches_many_short_segments_stay_in_few_batches() -> None:
    """812 short segments (like index.xhtml) must not create 23 batches."""
    from ai.epub_translate_roundtrip import plan_segment_batches

    segments = ["word" * 25 for _ in range(812)]  # ~100 chars each, 81K total
    batches = plan_segment_batches(segments, max_batch_chars=60_000)

    # Must be at most 2 batches (81K / 60K = 2), NOT 23
    assert len(batches) <= 2
    assert sum(len(b) for b in batches) == 812


def test_plan_segment_batches_short_segments_within_limit_are_one_batch() -> None:
    from ai.epub_translate_roundtrip import plan_segment_batches

    # 200 segments × 10 chars each = 2000 chars total — well within 60K
    segments = ["hello-ok!!" for _ in range(200)]
    batches = plan_segment_batches(segments, max_batch_chars=60_000)

    assert len(batches) == 1
    assert batches[0] == segments
```

- [ ] **Step 3: Run to verify all 4 test targets fail**

```bash
uv run pytest tests/unit/test_epub_translate_roundtrip.py::test_plan_segment_batches_enforces_char_limit_and_order tests/unit/test_epub_translate_roundtrip.py::test_plan_segment_batches_allows_single_oversized_segment tests/unit/test_epub_translate_roundtrip.py::test_plan_segment_batches_many_short_segments_stay_in_few_batches tests/unit/test_epub_translate_roundtrip.py::test_plan_segment_batches_short_segments_within_limit_are_one_batch -v 2>&1 | tail -15
```

Expected: TypeError on the two updated tests (`unexpected keyword argument 'max_batch_segments'`) and ImportError/assertion failures on the two new tests.

- [ ] **Step 4: Update constants and plan_segment_batches in epub_translate_roundtrip.py**

**4a.** Change lines 36–37:
```python
# Before:
_PRO_PREBATCH_MAX_CHARS = 18_000
_PRO_PREBATCH_MAX_SEGMENTS = 36

# After:
_PRO_PREBATCH_MAX_CHARS: int = 60_000  # TODO(SPEC-007): move to config.json
```

**4b.** Replace `plan_segment_batches` function (lines 326–361):

```python
def plan_segment_batches(
    segments: list[str],
    *,
    max_batch_chars: int,
) -> list[list[str]]:
    """Group segments into batches limited by total character count.

    A single segment that exceeds ``max_batch_chars`` is placed alone in its
    own batch (never split). Segment order is preserved across all batches.

    Args:
        segments: Flat list of segment strings to batch.
        max_batch_chars: Maximum total character count per batch (joining
            separators included).

    Returns:
        List of batches, each batch being a non-empty list of segments.
    """
    if max_batch_chars <= 0:
        raise ValueError("max_batch_chars must be > 0")
    if not segments:
        return []

    planned_batches: list[list[str]] = []
    current_batch: list[str] = []
    current_chars = 0

    for segment in segments:
        segment_len = len(segment)
        separator_len = len(_BATCH_SEPARATOR) if current_batch else 0
        next_chars = current_chars + separator_len + segment_len

        if current_batch and next_chars > max_batch_chars:
            planned_batches.append(current_batch)
            current_batch = [segment]
            current_chars = segment_len
            continue

        current_batch.append(segment)
        current_chars = next_chars

    if current_batch:
        planned_batches.append(current_batch)

    return planned_batches
```

**4c.** Update the call site (around line 578). Replace:
```python
planned_batches = plan_segment_batches(
    segment_texts,
    max_batch_chars=_PRO_PREBATCH_MAX_CHARS,
    max_batch_segments=_PRO_PREBATCH_MAX_SEGMENTS,
)
```
With:
```python
planned_batches = plan_segment_batches(
    segment_texts,
    max_batch_chars=_PRO_PREBATCH_MAX_CHARS,
)
```

- [ ] **Step 5: Run all tests**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```

Expected: all tests pass, 0 ruff errors

- [ ] **Step 6: Commit**

```bash
git add ai/epub_translate_roundtrip.py tests/unit/test_epub_translate_roundtrip.py
git commit -m "refactor: remove segment-count batch limit, use char-only batching at 60K"
```

---

## Task 3: Rate-Limit Backoff Retry + Pro Timeout

**Files:**
- Modify: `ai/epub_translate_roundtrip.py` (imports, constants, `translate_segments_with_batch_retry`, `batch_translate` closure)
- Test: `tests/unit/test_epub_translate_roundtrip.py`

### Background

`translate_segments_with_batch_retry` currently only catches `TimeoutExpired` and `ValueError`. When Gemini returns 429, a `RateLimitError` propagates uncaught and crashes the translation. This task adds: a rate-limit retry loop (sleep + retry same batch, up to 2 times), and a longer 5-minute timeout for Pro model batches.

---

- [ ] **Step 1: Write 5 new failing tests**

Add to `tests/unit/test_epub_translate_roundtrip.py`:

```python
def test_rate_limit_retry_sleeps_then_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """On RateLimitError, function sleeps using first backoff slot then retries."""
    import time
    from ai.epub_translate_roundtrip import translate_segments_with_batch_retry
    from ai.gemini_provider import RateLimitError

    sleep_calls: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleep_calls.append(s))

    call_count = 0

    def flaky_translate(text: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # fail only once — consumes backoff[0]=60
            raise RateLimitError("rate limited")
        return f"ZH:{text}"

    result = translate_segments_with_batch_retry(
        ["hello"],
        translate_batch=flaky_translate,
        context_label="test",
    )
    assert result == ["ZH:hello"]
    assert sleep_calls == [60]  # first backoff slot used


def test_rate_limit_retry_uses_retry_after_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    """When RateLimitError carries retry_after_seconds, that value is used instead of backoff."""
    import time
    from ai.epub_translate_roundtrip import translate_segments_with_batch_retry
    from ai.gemini_provider import RateLimitError

    sleep_calls: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleep_calls.append(s))

    call_count = 0

    def flaky_translate(text: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RateLimitError("rate limited", retry_after_seconds=45)
        return f"ZH:{text}"

    translate_segments_with_batch_retry(
        ["hello"],
        translate_batch=flaky_translate,
        context_label="test",
    )
    assert sleep_calls == [45]  # uses retry_after, not 60


def test_rate_limit_retry_exhausted_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """After both backoff slots consumed, RateLimitError propagates. Both sleep values are used."""
    import time
    from ai.epub_translate_roundtrip import translate_segments_with_batch_retry
    from ai.gemini_provider import RateLimitError

    sleep_calls: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleep_calls.append(s))

    def always_rate_limited(text: str) -> str:
        raise RateLimitError("always limited")

    with pytest.raises(RateLimitError):
        translate_segments_with_batch_retry(
            ["hello"],
            translate_batch=always_rate_limited,
            context_label="test",
        )
    # Both backoff slots are consumed (60s then 120s) before giving up
    assert sleep_calls == [60, 120]


def test_rate_limit_does_not_trigger_split(monkeypatch: pytest.MonkeyPatch) -> None:
    """RateLimitError retries the SAME batch, not a split sub-batch."""
    import time
    from ai.epub_translate_roundtrip import translate_segments_with_batch_retry
    from ai.gemini_provider import RateLimitError

    monkeypatch.setattr(time, "sleep", lambda s: None)

    received_lengths: list[int] = []

    def track_and_fail(text: str) -> str:
        # Count segments by separator count
        count = text.count("%%") + 1 if "%%" in text else 1
        received_lengths.append(count)
        if len(received_lengths) == 1:  # fail only once — one backoff slot consumed
            raise RateLimitError("limited")
        return "\n\n%%\n\n".join(f"ZH:{i}" for i in range(count))

    translate_segments_with_batch_retry(
        [f"seg{i}" for i in range(4)],
        translate_batch=track_and_fail,
        context_label="test",
    )
    # All calls should be for 4 segments (same batch), never 2+2 split
    assert all(n == 4 for n in received_lengths)


def test_pro_timeout_passed_to_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """batch_translate closure passes timeout_seconds=300 for Pro model."""
    import tempfile
    from pathlib import Path
    from ai import gemini_provider
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    received_timeout: list[int] = []

    def capture_translate(
        self: object,           # instance — required for class-level monkeypatch
        text: str,
        chunk_size: int,
        system_prompt: str,
        timeout_seconds: int = 180,
    ) -> str:
        received_timeout.append(timeout_seconds)
        count = text.count("%%") + 1 if "%%" in text else 1
        return "\n\n%%\n\n".join("ZH:seg" for _ in range(count))

    monkeypatch.setattr(gemini_provider.GeminiProvider, "translate_chunk", capture_translate)

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "book.epub"
        out = Path(tmp) / "out.epub"
        _build_min_epub(src)

        run_translate_roundtrip(
            source_epub=src,
            output_epub=out,
            output_lang="zh",
            bilingual_style="alternating",
            model="pro",  # resolves to _MODEL_ALIASES["pro"] = "gemini-3-pro-preview"
        )

    assert received_timeout and all(t == 300 for t in received_timeout)
```

- [ ] **Step 2: Run to verify tests fail**

```bash
uv run pytest tests/unit/test_epub_translate_roundtrip.py::test_rate_limit_retry_sleeps_then_retries tests/unit/test_epub_translate_roundtrip.py::test_rate_limit_retry_uses_retry_after_seconds tests/unit/test_epub_translate_roundtrip.py::test_rate_limit_retry_exhausted_raises tests/unit/test_epub_translate_roundtrip.py::test_rate_limit_does_not_trigger_split tests/unit/test_epub_translate_roundtrip.py::test_pro_timeout_passed_to_provider -v 2>&1 | tail -20
```

Expected: all FAIL (import errors or assertion failures)

- [ ] **Step 3: Update imports in epub_translate_roundtrip.py**

**3a.** Add `import time` to the imports block (after `import re`, before `import zipfile`).

**3b.** Update the `from ai.gemini_provider import GeminiProvider` line:
```python
from ai.gemini_provider import GeminiProvider, RateLimitError
```

- [ ] **Step 4: Add new constants after _PRO_PREBATCH_MAX_CHARS**

```python
_PRO_PREBATCH_MAX_CHARS: int = 60_000  # (already exists from Task 2)
_PRO_TIMEOUT_SECONDS: int = 300        # TODO(SPEC-007): move to config.json
_RATE_LIMIT_BACKOFF_SECONDS: list[int] = [60, 120]  # TODO(SPEC-007): move to config.json
```

- [ ] **Step 5: Replace translate_segments_with_batch_retry**

Replace the entire function (currently lines 387–436 after Task 2 changes):

```python
def translate_segments_with_batch_retry(
    segments: list[str],
    *,
    translate_batch: TranslateFn,
    context_label: str,
    retry_depth: int = 0,
    rate_limit_retry_count: int = 0,
) -> list[str]:
    expected_count = len(segments)
    if expected_count == 0:
        return []

    batch_text = join_segments_for_batch(segments)

    def split_and_retry(reason: str, exc: Exception) -> list[str]:
        if expected_count == 1:
            raise RuntimeError(
                f"Batch translation failed at minimal granularity for {context_label}: {reason}"
            ) from exc

        split_index = expected_count // 2
        print(
            f"[WARN] [{context_label}] {reason} at depth={retry_depth}, "
            f"splitting {expected_count} -> {split_index}+{expected_count - split_index}",
            flush=True,
        )

        left = translate_segments_with_batch_retry(
            segments[:split_index],
            translate_batch=translate_batch,
            context_label=context_label,
            retry_depth=retry_depth + 1,
            # rate_limit_retry_count resets to 0: each sub-batch has its own retry budget
        )
        right = translate_segments_with_batch_retry(
            segments[split_index:],
            translate_batch=translate_batch,
            context_label=context_label,
            retry_depth=retry_depth + 1,
        )
        return left + right

    try:
        translated_batch = str(translate_batch(batch_text))
    except RateLimitError as exc:
        if rate_limit_retry_count >= len(_RATE_LIMIT_BACKOFF_SECONDS):
            raise
        wait = (
            exc.retry_after_seconds
            if exc.retry_after_seconds is not None
            else _RATE_LIMIT_BACKOFF_SECONDS[rate_limit_retry_count]
        )
        print(
            f"[WARN] [{context_label}] Rate limited. Waiting {wait}s before retry "
            f"(attempt {rate_limit_retry_count + 1}/{len(_RATE_LIMIT_BACKOFF_SECONDS)}).",
            flush=True,
        )
        time.sleep(wait)
        return translate_segments_with_batch_retry(
            segments,
            translate_batch=translate_batch,
            context_label=context_label,
            retry_depth=retry_depth,
            rate_limit_retry_count=rate_limit_retry_count + 1,
        )
    except subprocess.TimeoutExpired as exc:
        timeout_value = exc.timeout if isinstance(exc.timeout, (int, float)) else "unknown"
        return split_and_retry(f"Batch request timed out after {timeout_value}s", exc)

    try:
        return split_batch_translation(translated_batch, expected_count=expected_count)
    except ValueError as exc:
        return split_and_retry("Batch output mismatch", exc)
```

- [ ] **Step 6: Update batch_translate closure to pass Pro timeout**

Find the `batch_translate` closure (around current line 564) and replace it:

```python
def batch_translate(batch_text: str) -> str:
    if translate_fn is not None:
        return str(translate_fn(batch_text))
    if prompt is None:
        raise RuntimeError("translation prompt must be initialized")
    return provider.translate_chunk(
        text=batch_text,
        chunk_size=len(batch_text),
        system_prompt=prompt,
        timeout_seconds=_PRO_TIMEOUT_SECONDS if is_pro_model else 180,
    )
```

- [ ] **Step 7: Run all tests**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q && bash -n translatebook.sh
```

Expected: all tests pass, 0 ruff errors

- [ ] **Step 8: Commit**

```bash
git add ai/epub_translate_roundtrip.py tests/unit/test_epub_translate_roundtrip.py
git commit -m "fix: add rate-limit backoff retry and Pro timeout to EPUB translate workflow"
```

---

## Verification Checklist (all three commits)

```bash
uv run ruff check .           # 0 errors
uv run ruff format --check .  # no diffs
uv run pytest -q              # all green
bash -n translatebook.sh      # shell syntax valid
```

## Risk Notes

- `test_pro_timeout_passed_to_provider` uses `monkeypatch.setattr(gemini_provider.GeminiProvider, "translate_chunk", capture_translate)` with `self` as first param — this correctly patches the class method and intercepts the bound call inside the closure.
- `time.sleep` must be monkeypatched in all rate-limit retry tests — tests that actually sleep 60s will time out CI. The `monkeypatch` fixture in pytest handles cleanup automatically.
- After Task 2, `plan_segment_batches` no longer validates `max_batch_segments <= 0`. The `ValueError` for `max_batch_chars <= 0` is preserved. No existing test checks the removed validation.
