# Design: EPUB Translation Batching & Rate-Limit Handling

**Date:** 2026-03-23
**Branch:** `fix/epub-batching-rate-limit`
**Scope:** `ai/epub_translate_roundtrip.py`, `ai/gemini_provider.py`

---

## Problem Statement

The Pro model EPUB translation workflow has two independent failures:

### Failure 1 — Too Many API Calls (Rate Limit)

`_PRO_PREBATCH_MAX_SEGMENTS = 36` was the wrong batching metric. Segment count is not correlated with translation time — what matters is total character count per batch. For pages with many short segments (e.g. `index.xhtml` with 812 segments × ~100 chars each), the segment limit triggers long before the char limit, creating 23 separate API calls for a single chapter. This exhausts the short-window RPM rate limit and causes a 429 crash.

```
index.xhtml: 812 segments × ~100 chars = ~81K chars total
Before:  23 batches (36 seg limit triggers first) → 429
After:   2 batches (60K char limit)               → OK
```

### Failure 2 — 429 Not Caught

`translate_segments_with_batch_retry` only catches `subprocess.TimeoutExpired` and `ValueError` (segment count mismatch). A 429 from Gemini CLI raises `RuntimeError`, which propagates uncaught and crashes the translation. Rate limit errors require a different response (wait and retry the same batch), not the existing split-retry logic.

---

## Non-Goals

- SPEC-007 (unified config management) — constants are marked `TODO(SPEC-007)` for future extraction
- Changes to Flash model strategy (Flash has no pre-batching; this is intentional and unchanged)
- Prompt selection / A/B testing (separate initiative)
- Changes to `03_translate_md.py` pipeline or `GeminiProvider` usage outside EPUB workflow

---

## Design

### Constants (all in `epub_translate_roundtrip.py`)

```python
_PRO_PREBATCH_MAX_CHARS: int = 60_000
# Removed: _PRO_PREBATCH_MAX_SEGMENTS = 36
_PRO_TIMEOUT_SECONDS: int = 300
_RATE_LIMIT_BACKOFF_SECONDS: list[int] = [60, 120]
# TODO(SPEC-007): move _PRO_PREBATCH_MAX_CHARS, _PRO_TIMEOUT_SECONDS,
# and _RATE_LIMIT_BACKOFF_SECONDS to config.json epub_workflow section
```

### Change 1 — Char-Only Batching

Remove `max_batch_segments` from `plan_segment_batches`. The function signature becomes:

```python
def plan_segment_batches(
    segments: list[str],
    max_batch_chars: int,
) -> list[list[str]]: ...
```

The segment count parameter is removed entirely (not made optional) to prevent future misuse.

Pro pre-batching call site:
```python
if is_pro_model:
    planned_batches = plan_segment_batches(
        segment_texts,
        max_batch_chars=_PRO_PREBATCH_MAX_CHARS,
    )
```

Flash strategy unchanged: `planned_batches = [segment_texts]` (single batch, no limit).

### Change 2 — `RateLimitError` in `gemini_provider.py`

New exception class:

```python
class RateLimitError(RuntimeError):
    """Raised when Gemini CLI returns 429 / RESOURCE_EXHAUSTED."""
    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
```

Helper to parse wait time from CLI stderr (best-effort; falls back to hardcoded backoff if absent):

```python
def _parse_retry_after(stderr: str) -> int | None:
    """Extract retry delay from Gemini CLI stderr. Returns None if not present."""
    m = re.search(r'"retryDelay":\s*"(\d+)s"', stderr)
    if m:
        return int(m.group(1))
    m = re.search(r'retry after (\d+)', stderr, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None
```

Updated `translate_chunk` error handling:

```python
if result.returncode != 0:
    stderr = (result.stderr or "").strip()
    if "429" in stderr or "RESOURCE_EXHAUSTED" in stderr:
        wait = _parse_retry_after(stderr)
        raise RateLimitError(f"Gemini rate limited: {stderr}", retry_after_seconds=wait)
    raise RuntimeError(f"Gemini CLI failed: {stderr}")
```

### Change 3 — Rate-Limit Retry in `translate_segments_with_batch_retry`

Add a `rate_limit_retry_count` parameter (default 0). On `RateLimitError`:
- Compute wait: `exc.retry_after_seconds` if available, else `_RATE_LIMIT_BACKOFF_SECONDS[rate_limit_retry_count]`
- Sleep and retry the **same batch** (not split — splitting increases call count, making rate limiting worse)
- After `len(_RATE_LIMIT_BACKOFF_SECONDS)` attempts, raise to caller

Error routing summary:

| Exception | Action |
|-----------|--------|
| `RateLimitError` | sleep(retry_after or backoff[n]) → retry same batch → raise after max retries |
| `TimeoutExpired` | split-retry (existing behavior) |
| `ValueError` (count mismatch) | split-retry (existing behavior) |
| `RuntimeError` (other CLI error) | raise immediately |

### Change 4 — Pro Timeout

`batch_translate` closure passes `timeout_seconds` based on model:

```python
def batch_translate(batch_text: str) -> str:
    return provider.translate_chunk(
        text=batch_text,
        chunk_size=len(batch_text),
        system_prompt=prompt,
        timeout_seconds=_PRO_TIMEOUT_SECONDS if is_pro_model else 180,
    )
```

`GeminiProvider.translate_chunk` signature unchanged (`timeout_seconds: int = 180`).

---

## File Changes

| File | Change |
|------|--------|
| `ai/gemini_provider.py` | Add `RateLimitError`, `_parse_retry_after`, update `translate_chunk` error branch |
| `ai/epub_translate_roundtrip.py` | Remove `_PRO_PREBATCH_MAX_SEGMENTS`, add `_PRO_TIMEOUT_SECONDS` + `_RATE_LIMIT_BACKOFF_SECONDS`, update `plan_segment_batches` call, update `translate_segments_with_batch_retry` |
| `tests/unit/test_gemini_provider.py` | Tests for `RateLimitError` raise, `_parse_retry_after` parsing |
| `tests/unit/test_epub_translate_roundtrip.py` | Tests for char-only batching, rate-limit retry backoff, timeout passthrough |

---

## Test Plan (TDD)

### `test_gemini_provider.py`

| Test | Behavior |
|------|----------|
| `test_rate_limit_error_raised_on_429` | stderr with "RESOURCE_EXHAUSTED" → `RateLimitError` |
| `test_runtime_error_raised_on_other_failure` | returncode != 0, no 429 signal → `RuntimeError` |
| `test_parse_retry_after_json_format` | `"retryDelay": "45s"` → 45 |
| `test_parse_retry_after_natural_language` | `"retry after 30 seconds"` → 30 |
| `test_parse_retry_after_missing` | no pattern → `None` |

### `test_epub_translate_roundtrip.py`

| Test | Behavior |
|------|----------|
| `test_plan_segment_batches_char_only` | 812 × 100-char segments, max=60K → ≤ 2 batches |
| `test_plan_segment_batches_no_segment_limit` | 200 segments × 10 chars each, max=60K → 1 batch |
| `test_rate_limit_retry_uses_backoff` | `RateLimitError` → sleep(60) → retry → `RateLimitError` → sleep(120) → retry → succeed |
| `test_rate_limit_retry_uses_retry_after` | `RateLimitError(retry_after_seconds=45)` → sleep(45) not 60 |
| `test_rate_limit_exhausted_raises` | 3× `RateLimitError` → `RateLimitError` propagates |
| `test_rate_limit_does_not_split` | `RateLimitError` on 36-segment batch → retry same 36, not split 18+18 |
| `test_pro_timeout_passed_to_provider` | Pro model → `translate_chunk` called with `timeout_seconds=300` |

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| 60K chars causes Pro timeout on content-heavy chapters | `TimeoutExpired` split-retry still active as safety net |
| `_parse_retry_after` misparses CLI output | Unit tests cover both formats + None fallback; fallback to hardcoded values is safe |
| `rate_limit_retry_count` threading/recursion confusion | Parameter is explicit, not global state; recursion depth limited by `len(_RATE_LIMIT_BACKOFF_SECONDS)` |
| `plan_segment_batches` callers break after removing `max_batch_segments` | Only one call site in production code; test suite catches signature errors immediately |
