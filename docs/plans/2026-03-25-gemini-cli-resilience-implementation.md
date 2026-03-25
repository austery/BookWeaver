# Gemini CLI Resilience Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `--provider cli` robust for large EPUB chapters by preferring longer wait + bounded retries before split fallback, so timeout/AbortError cascades are reduced.

**Architecture:** Keep the current CLI provider path and checkpoint semantics. Add typed transient CLI error classification in `ai/gemini_provider.py`, then update `translate_segments_with_batch_retry()` in `ai/epub_translate_roundtrip.py` to use configurable wait-first retry policy before split, with a split-depth cap. Cover with TDD at unit + integration level.

**Tech Stack:** Python 3.13+, pytest, ruff, shell script runner (`translatebook.sh`)

---

### Task 1: Add failing tests for CLI transient error classification

**Files:**
- Modify: `tests/unit/test_gemini_provider.py`
- Modify: `ai/gemini_provider.py`

**Step 1: Write the failing test**

Add tests asserting:
- `AbortError: The user aborted a request.` is classified as transient retryable error
- Existing `RateLimitError` behavior remains unchanged

```python
def test_abort_error_raised_as_transient_cli_error(monkeypatch):
    from ai.gemini_provider import GeminiProvider, TransientCLIError
    ...
    with pytest.raises(TransientCLIError):
        provider.translate_chunk(...)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_gemini_provider.py::test_abort_error_raised_as_transient_cli_error`  
Expected: FAIL (class not found or wrong exception type)

**Step 3: Write minimal implementation**

In `ai/gemini_provider.py`:
- Add `TransientCLIError(RuntimeError)` with optional `retry_after_seconds`
- In CLI stderr parsing, detect AbortError pattern and raise `TransientCLIError`

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_gemini_provider.py -q`  
Expected: PASS for new and existing provider tests

**Step 5: Commit**

```bash
git add tests/unit/test_gemini_provider.py ai/gemini_provider.py
git commit -m "test: classify Gemini CLI AbortError as transient retryable"
```

### Task 2: Add failing tests for wait-first timeout/abort strategy

**Files:**
- Modify: `tests/unit/test_epub_translate_roundtrip.py`
- Modify: `ai/epub_translate_roundtrip.py`

**Step 1: Write the failing tests**

Add tests for `translate_segments_with_batch_retry()`:
- timeout should retry same batch first (no immediate split)
- transient abort should retry same batch first
- split only after retry budget exhausted
- split depth cap blocks deeper recursion and raises clear error

```python
def test_timeout_retries_before_split(monkeypatch):
    ...
    assert received_batch_sizes[:2] == [172, 172]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_timeout_retries_before_split`  
Expected: FAIL (current behavior splits immediately on timeout)

**Step 3: Write minimal implementation**

In `ai/epub_translate_roundtrip.py`:
- Add config constants for timeout/abort retries and backoff
- Add retry branches for `subprocess.TimeoutExpired` and `TransientCLIError`
- Delay split until retry budget consumed
- Add split depth guard (`CLI_MAX_SPLIT_DEPTH`)

**Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -q`  
Expected: PASS for new and existing roundtrip tests

**Step 5: Commit**

```bash
git add tests/unit/test_epub_translate_roundtrip.py ai/epub_translate_roundtrip.py
git commit -m "feat: add wait-first retry policy before CLI timeout split"
```

### Task 3: Add configuration wiring for tunable retry/timeout knobs

**Files:**
- Modify: `ai/epub_translate_roundtrip.py`
- Modify: `09_epub_translate_roundtrip.py`
- Modify: `config/config.json.example`
- Modify: `README.md`

**Step 1: Write failing config tests**

Add tests asserting config/env knobs are loaded and applied:
- timeout seconds
- abort retries/backoff
- timeout retries/backoff
- split depth cap

**Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -k "cli_resilience"`  
Expected: FAIL (knobs not wired yet)

**Step 3: Write minimal implementation**

Implement precedence (recommended):
1. CLI args (if introduced)
2. env vars
3. config (`config/config.json`)
4. code defaults

Keep change minimal: start with env + code defaults, then config json mapping.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -q`  
Expected: PASS

**Step 5: Commit**

```bash
git add ai/epub_translate_roundtrip.py 09_epub_translate_roundtrip.py config/config.json.example README.md tests/unit/test_epub_translate_roundtrip.py
git commit -m "feat: add configurable CLI resilience knobs for timeout and retries"
```

### Task 4: Add integration test for chapter3-like large batch behavior

**Files:**
- Modify: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Write failing integration-style test**

Simulate ~172 segments timeout pattern:
- first attempt timeout
- one retry on same batch
- then either succeed or split within depth cap

Assert:
- no immediate split before retry
- split depth never exceeds configured max

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_large_batch_wait_first_then_split`  
Expected: FAIL on current logic mismatch

**Step 3: Minimal fix/refactor**

Adjust retry bookkeeping to ensure deterministic behavior under nested recursion.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -q`  
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_epub_translate_roundtrip.py ai/epub_translate_roundtrip.py
git commit -m "test: validate large chapter CLI timeout resilience flow"
```

### Task 5: End-to-end verification and documentation polish

**Files:**
- Modify: `README.md`
- Optionally modify: `docs/plans/2026-03-25-gemini-cli-resilience-design.md` (status note)

**Step 1: Update README usage**

Document:
- recommended CLI resilience defaults
- how to tune knobs safely
- warning about too many retries consuming quota

**Step 2: Run full project checks**

Run:
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest -q`
- `bash -n translatebook.sh`

Expected: all pass

**Step 3: Smoke test command**

Run one real smoke command (user sample):
`./translatebook.sh --workflow epub --provider cli --model flash <epub>`

Expected:
- timeout logs show retry-first behavior
- no immediate split on first timeout

**Step 4: Final commit**

```bash
git add README.md docs/plans/2026-03-25-gemini-cli-resilience-design.md
git commit -m "docs: add CLI resilience tuning guidance and verification notes"
```

