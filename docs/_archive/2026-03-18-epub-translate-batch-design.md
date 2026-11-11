# EPUB Translate Roundtrip Batch Prompt Design

## Context

Current package-aware translation roundtrip (`--epub-translate-roundtrip`) translates one extracted text segment per Gemini call.

For long chapters, this creates very high request counts and quickly exhausts model-specific quota (especially on `flash`), even when overall account capacity still exists on other models.

## Goal

- Reduce call count dramatically by batching segments per chapter/document.
- Keep strict structural guarantees (same segment count, anchor-safe patching, integrity checks).
- Keep feature behind existing optional flag and do not change legacy markdown pipeline.

## Non-Goals

- No model fallback chain in this task.
- No replacement of default translation path.
- No change to bilingual style scope (`alternating` only).

## Prompt Strategy Decision

Use Immersive-style prompt rules for batch mode only:

- Enforce translation-only output.
- Enforce paragraph/segment count preservation.
- Use `%%` as multi-segment delimiter.
- Keep legacy prompt behavior unchanged for old markdown flow.

This avoids cross-mode coupling and keeps migration risk low.

## Approaches Considered

### A. Chapter-level batch with `%%` + strict split validation + binary retry (Recommended)

Flow:

1. Collect all translatable segments of one spine XHTML.
2. Join with `\n\n%%\n\n` and send in one request.
3. Split output by `%%` and verify count equality.
4. If mismatch, recursively split segment list and retry smaller chunks.
5. If minimal chunk still mismatches, fail fast.

Pros:
- Major reduction in API calls.
- Strong output alignment guarantees.
- Works with existing patching/integrity pipeline.

Cons:
- Requires robust batch parser/retry control.

### B. Fixed-size batches only (no recursive retry)

Pros:
- Simpler implementation.

Cons:
- Fragile when model output occasionally drifts from expected separator format.

### C. Keep per-segment calls and only tweak prompt

Pros:
- Minimal code changes.

Cons:
- Call count problem remains; quota pressure largely unchanged.

## Chosen Design

### 1) Architecture

Inside `ai/epub_translate_roundtrip.py`, replace per-segment request loop with batch translation per XHTML document:

- Build batch payload from extracted segments.
- Translate in bulk using a batch prompt renderer.
- Recover translations by strict delimiter parsing.
- Reuse existing alternating patch + integrity validation + repack steps.

### 2) Data Flow

For each translatable XHTML doc:

1. `extract_translatable_segments(xhtml)` -> `segments`.
2. `segments -> batch_text` (`%%` delimiter).
3. `GeminiProvider.translate_chunk(batch_text, ...)`.
4. Parse output into `translations`.
5. Validate `len(translations) == len(segments)`.
6. On mismatch: binary split and retry.
7. `patch_xhtml_alternating(xhtml, translations)`.

### 3) Error Handling

- Any unresolved count mismatch after binary retry -> hard failure.
- Any Gemini CLI runtime error -> hard failure (existing behavior).
- Integrity errors remain fail-fast before repack.

### 4) Observability

Add progress logs:

- Per-doc segment count
- Batch mode indicator
- Retry/split events on mismatch
- Final translated docs/segments summary

## Acceptance Criteria

- API calls are reduced from per-segment to per-document-or-sub-batch.
- `%%` batch parsing preserves one-to-one segment alignment.
- Existing anchor/structure/integrity guarantees remain valid.
- Existing tests pass, with new tests covering batching and retry behavior.
- End-to-end run on large chapter proceeds with significantly fewer requests.
