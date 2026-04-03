# EPUB Segment Scaffolding Design (Minimal Change)

## Problem

Post-refactor EPUB translation quality regressed in some cases, especially in tone-sensitive prose. We validated two likely contributors:

1. Prompt simplification from legacy immersive format to a generic format.
2. Weak segment boundary contract in multi-segment payloads.

This design addresses only one variable first: restore **strong segment boundary scaffolding** for EPUB, while keeping architecture and batching logic unchanged.

## Scope

### In Scope

- EPUB path only.
- Default-on segment scaffolding protocol for multi-segment batches.
- Protocol implementation at provider adapter protocol layer.
- TDD for serializer/parser and EPUB wiring behavior.

### Out of Scope (this iteration)

- Changing `TextBatcher` algorithm.
- Enforcing doc-boundary flush batching.
- New CLI flags for protocol selection.
- Markdown/PDF protocol changes.

## Decision Summary

- Approach selected: **Adapter-layer protocol replacement** (EPUB only), not CLI-layer and not full strategy-object refactor.
- Default behavior: **enabled by default** for EPUB.
- Core/engine isolation: `TranslationEngine` and `TextBatcher` remain unchanged.

## Design

## 1. Architecture placement

Restore scaffolding as a transport protocol concern in:

- `ai/adapters/providers/_delimiter.py`

Rationale:

- This module already owns batch join/split protocol.
- Keeps hexagonal boundaries clean: core sees plain segment lists only.
- Avoids leaking protocol details into CLI/composition root.

## 2. Protocol contract

For EPUB multi-segment batches, serialize as tagged blocks instead of plain delimiter-only payload.

### Request format (conceptual)

```xml
<segment id="1">
...
</segment>
<segment id="2">
...
</segment>
```

### Output contract

Model must return the same segment ids and count.

Validation rules:

1. Extract `id -> content` by tag parsing.
2. Ensure IDs are present, unique, and contiguous from `1..N`.
3. Ensure parsed count equals expected count.
4. On any mismatch, raise `TranslationError` (existing split-retry path handles recovery).

Single-segment path keeps existing simple behavior.

## 3. Prompt addendum update (EPUB mode)

For EPUB multi-segment batches, adapter-level prompt addendum should require:

- Keep `<segment id="n">` wrapper in output.
- Preserve one-to-one segment mapping.
- No merge/split/add/delete of segments.

This is an additive instruction, not a core prompt overhaul.

## 4. Data flow

1. Engine emits list of pending segment texts.
2. Provider adapter calls protocol join function.
3. EPUB mode + multi-segment -> tagged scaffolding payload.
4. Model returns translated text.
5. Protocol split parses tags and validates structure.
6. On parse mismatch -> `TranslationError` -> existing recursive split-retry behavior.

## 5. Error handling

- Parse or structural mismatch: `TranslationError` with concise reason.
- Do not silently coerce malformed outputs.
- Keep existing retry/split pipeline unchanged.

## 6. Testing plan (TDD)

## Unit tests

### `tests/unit/test_adapter_providers.py`

- `join_segments` EPUB/multi produces tagged scaffold format.
- `split_response` parses valid tagged output correctly.
- Invalid cases raise `TranslationError`:
  - missing tag
  - duplicated id
  - out-of-order/non-contiguous ids
  - count mismatch

### `tests/unit/test_cli.py`

- EPUB path uses protocol mode by default (wiring/assertion level).
- Non-EPUB paths remain on existing behavior.

## Regression checks

- Run:
  - `uv run pytest -q tests/unit/test_adapter_providers.py`
  - `uv run pytest -q tests/unit/test_cli.py`
- Re-run Chapter 1 Flash A/B once for sanity (no quality claim gate, only structural stability and parse correctness).

## 7. Rollout and risk

### Risks

- Tag parsing brittleness with unexpected model formatting.
- Over-constrained output causing occasional retries.

### Mitigations

- Keep fallback split-retry path unchanged.
- Restrict rollout to EPUB only in this iteration.
- Preserve single-segment fast path.

## 8. Acceptance criteria

1. EPUB multi-segment payloads use tagged scaffolding by default.
2. Parser strictly validates segment id/count mapping.
3. Unit tests for valid and invalid protocol behavior pass.
4. No changes to batch algorithm or doc-boundary policy in this change.

## 9. Next iteration (not in this change)

- Optional doc-boundary batching mode (`flush-on-doc-change`) for prose-heavy books.
- Optional format/profile matrix for protocol selection (EPUB fiction vs technical).
