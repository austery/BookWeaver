# Pro Model Timeout Mitigation via Pre-Batching Design

Date: 2026-03-21
Project: BookWeaver
Status: Approved

## 1. Problem

When running EPUB workflow with `--model pro` (resolved to `gemini-3-pro-preview`), large chapter-level batch requests frequently hit client timeout (`180s`), then fall back to recursive split-retry.

Observed case:

- File: `Analytics Engineering With SQL and Dbt_ Bu - Rui Pedro Machado.epub`
- Chapter: `OEBPS/ch01.html`
- Segments: `130`
- First-request payload size: about `54,221` characters
- Prompt size: about `909` characters
- Runtime logs: repeated timeout warnings at depth `0..2`, then split into smaller batches

## 2. Root Cause Analysis

1. The main bottleneck is oversized single requests for Pro, not prompt length.
2. Existing logic is reactive:
   - try very large batch first
   - timeout
   - split and retry recursively
3. Prompt is **not** lost during split. Every sub-batch still carries the same system/custom prompt.
4. Waste comes from timed-out requests that were already processed server-side before client timeout was raised.

## 3. Options Considered

### A) Pre-batch limits before first request (Recommended)

- Add deterministic planning before translation:
  - `max_batch_chars`
  - `max_batch_segments`
- Then each planned sub-batch still uses existing split-retry fallback.

Pros:

- Reduces timeout probability before first expensive call
- Preserves current reliability fallback
- Predictable and easy to reason about

Cons:

- Prompt repeated across more requests (small overhead)

### B) Increase timeout only

Pros:

- Very small code change

Cons:

- Does not reduce oversized requests
- Can increase wall-clock time and still fail
- More exposed to uncertain network/service latency

### C) Auto-downgrade model after timeout

Pros:

- Controls failure rate and latency in worst-case scenarios

Cons:

- Behavior change in output quality
- Needs explicit product policy and user expectation handling

## 4. Approved Approach

Use **Option A** for this phase.

For Pro in EPUB workflow, apply balanced pre-batch limits:

- `max_batch_chars = 18000`
- `max_batch_segments = 36`

Real-case estimate (`ch01`, 130 segments):

- No pre-batching: 1 batch ~53.3k chars (high timeout risk)
- Balanced pre-batching: 4 batches `[33, 36, 36, 25]`
- Prompt overhead increase: about `6.4%` (acceptable)

## 5. Architecture and Data Flow

### New component

Add a pure planner function in `ai/epub_translate_roundtrip.py`:

- Input: ordered segment texts, batch limits
- Output: ordered `list[list[str]]` (planned batches)
- Guarantees:
  - stable ordering
  - no dropped segments
  - no empty batch
  - each batch satisfies both limits except unavoidable single-segment oversize case

### Updated flow per chapter

1. Extract chapter segments
2. Plan batches using configured limits
3. For each planned batch:
   - call existing `translate_segments_with_batch_retry(...)`
   - preserve current timeout mismatch split behavior
4. Concatenate translated sub-results in original order
5. Patch XHTML and write checkpoint as before

## 6. Error Handling

No silent fallback and no broad catch additions.

- Keep existing fail-fast behavior:
  - if minimal granularity (`1` segment) still times out, raise `RuntimeError`
- Keep checkpoint semantics unchanged:
  - completed chapters remain resumable
  - failed chapter stops run and can resume later

## 7. Observability

Add chapter-level batch planning logs:

- `planned_batches=<n>`
- per batch: `segments=<x>`, `chars=<y>`

Retain existing warning logs:

- timeout split depth
- mismatch split depth

## 8. Test Strategy (TDD)

1. Add failing unit tests for planner:
   - deterministic split for known segment sets
   - enforce both limits
   - preserve total segment count and order
2. Add failing roundtrip behavior test:
   - chapter translation uses multiple planned batches under chosen limits
   - aggregated output order remains correct
3. Keep and pass existing timeout split tests to ensure backward compatibility

## 9. Scope and Non-Goals

In scope:

- EPUB workflow pre-batching for Pro timeout mitigation
- Logging improvements for planned batches

Out of scope for this change:

- automatic model downgrade policy
- global timeout policy redesign
- prompt quality optimization branch work

## 10. Acceptance Criteria

Design is successful when:

1. Pro workflow no longer starts large >50k-char chapter requests for similar books
2. Timeout warning frequency decreases materially on large chapters
3. Existing integrity and checkpoint behavior remains unchanged
4. Tests cover planner correctness and integration behavior
