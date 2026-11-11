# Gemini CLI Resilience Design (CLI-Only Path)

Date: 2026-03-25  
Project: BookWeaver  
Status: Approved

## 1. Problem

In EPUB workflow with `--provider cli`, large chapters can trigger repeated timeout-driven split cascades:

- Example: `chapter3.xhtml (segments=172)`
- Current behavior:
  - timeout after `180s` at depth 0
  - immediate binary split
  - repeated timeout + split (depth grows to 6+)
  - eventual failure at minimal granularity

This causes high request churn, long runtime, and poor completion rate for large documents.

## 2. User Goals

1. Keep Gemini CLI as primary path (no automatic provider switch to API).
2. Prefer waiting longer on large batch requests before splitting.
3. Keep retry count low to avoid excessive quota burn.
4. Make backoff/timeout configurable.

## 3. Chosen Approach (Approved)

Implement a **wait-first, split-later** strategy for CLI mode:

1. Add configurable CLI timeout and retry settings.
2. Classify Gemini CLI `AbortError` as retryable transient failure.
3. For timeout/abort:
   - retry same batch first (small retry budget),
   - only then allow split fallback.
4. Cap split depth to prevent pathological recursive split chains.

## 4. Configuration Plan

Add runtime knobs (env or config-backed later):

- `CLI_TIMEOUT_SECONDS` (default target: `720`)
- `CLI_ABORT_RETRIES` (default target: `1`)
- `CLI_ABORT_BACKOFF_SECONDS` (default target: `45`)
- `CLI_TIMEOUT_RETRIES` (default target: `1`)
- `CLI_TIMEOUT_BACKOFF_SECONDS` (default target: `60`)
- `CLI_SPLIT_ON_TIMEOUT` (default target: `false`)
- `CLI_FORCE_SPLIT_AFTER_ATTEMPTS` (default target: `2`)
- `CLI_MAX_SPLIT_DEPTH` (default target: `4`)

### Initial Recommended Defaults

For large-book CLI stability (user-approved):

- timeout: 12 minutes (`720s`)
- timeout retries: 1
- abort retries: 1
- split only after attempts exhausted
- max split depth: 4

## 5. Architecture Changes

### 5.1 `ai/gemini_provider.py`

- Add transient error classification for CLI stderr:
  - `AbortError: The user aborted a request.`
- Introduce `TransientCLIError` (or equivalent typed runtime error)
- Keep existing `RateLimitError` behavior unchanged.

### 5.2 `ai/epub_translate_roundtrip.py`

Update `translate_segments_with_batch_retry()` flow:

1. On timeout/transient abort:
   - retry same batch with configured backoff (low retry budget)
2. If retry budget exhausted:
   - if split allowed and within depth limit, split and recurse
   - else fail fast with clear error
3. Enforce split depth guard (`CLI_MAX_SPLIT_DEPTH`).

## 6. Logging/Observability

Add explicit logs to distinguish retry vs split decisions:

- `Timeout. Retrying same batch (attempt x/y, wait=zs)`
- `Transient abort. Retrying same batch ...`
- `Retry budget exhausted. Splitting batch ...`
- `Split blocked by max depth ... failing`

This makes behavior audit-friendly and easier to tune.

## 7. Test Strategy (TDD)

### Unit Tests

1. `AbortError` stderr is classified as transient retryable error.
2. Timeout path retries same batch first (no immediate split).
3. After retry budget exhaustion, split fallback is invoked.
4. Split depth cap is honored and stops recursion beyond configured max.

### Integration Tests

1. Large synthetic chapter (~172 segments) with mocked timeout pattern:
   - verify no split before retry budget is consumed.
2. Ensure depth never exceeds configured `CLI_MAX_SPLIT_DEPTH`.

## 8. Non-Goals

- No automatic CLI→API failover in this change.
- No model auto-switch policy changes in this change.
- No prompt strategy changes in this change.

## 9. Acceptance Criteria

1. CLI workflow avoids immediate split on first timeout for large chapters.
2. Retry attempts are bounded and configurable.
3. Split depth is capped and observable.
4. Existing rate-limit logic continues to work.
5. Regression tests pass and new behavior is covered by tests.

