# EPUB Translate Roundtrip Design

## Context

Baseline roundtrip mode is already implemented (`--epub-baseline`) and proves package-preserving repack with strict integrity checks.

Translation output is still on the legacy markdown-render-convert path, which can drift from source EPUB structure for anchors, navigation, and package fidelity.

## Goal

- Add an optional package-aware translation mode that keeps EPUB structure and resources intact while translating body content.
- Produce bilingual output in existing `alternating` style.
- Keep this mode behind an explicit CLI flag so current default behavior stays unchanged.

## Non-Goals

- No replacement of default pipeline in this phase.
- No new bilingual layouts beyond `alternating`.
- No mutation of nav/toc documents in phase 1.

## Approaches Considered

### A. Optional package-aware translate roundtrip (Recommended)

`EPUB load -> spine XHTML text-node extraction -> Gemini translation -> alternating patch -> integrity checks -> repack`

Pros:
- Lowest migration risk (feature flag rollout).
- Highest structure fidelity.
- Easy rollback to current default path.

Cons:
- Requires new XHTML patching utilities and dedicated tests.

### B. Legacy markdown translation + reinjection

Pros:
- Reuses existing translation chunking path.

Cons:
- Hard to preserve anchor/nav semantics.
- Higher mismatch risk between patched and source package documents.

### C. Direct replacement of current default flow

Pros:
- Single unified translation path.

Cons:
- Highest rollout risk and regression blast radius.

## Chosen Design

### 1) Architecture

Introduce a new optional mode in `translatebook.sh`:

- `--epub-translate-roundtrip`

When enabled:

1. Load package model from source EPUB.
2. Select translatable XHTML docs from OPF spine.
3. Extract translatable body text nodes.
4. Translate through Gemini CLI with existing prompt/profile/model selection conventions.
5. Patch XHTML into bilingual alternating output while preserving ids/classes/hrefs and document order.
6. Run strict integrity checks (cover/toc pointers, asset existence, fragment targets).
7. Repack to `<temp_dir>/translated_roundtrip.epub`.

### 2) Data and Mutation Boundaries

- Mutate only body text content in spine XHTML docs.
- Keep nav/toc files untouched by default.
- Keep OPF manifest/spine ordering untouched.
- Preserve all non-text resources (images/css/fonts) and relative paths.

### 3) Error Handling Policy

Strict mode only (phase 1):

- Any integrity error is fatal and exits non-zero.
- No warning-only continuation.
- No silent fallback to legacy pipeline.

### 4) Validation

Required checks before success:

- Package structure valid (cover/toc/spine references resolvable).
- No missing manifest assets.
- No broken fragment links (including cross-document anchors).
- Repacked EPUB produced at expected path.

## Acceptance Criteria

- `translatebook.sh` supports `--epub-translate-roundtrip`.
- New mode runs without changing default pipeline behavior.
- Bilingual alternating content appears in spine XHTML docs in output EPUB.
- nav/toc resources remain unmodified by translation mode.
- Integrity failures stop execution and return non-zero.
- Unit tests and repository quality gates pass.

## Rollout

1. Behind explicit flag only.
2. Validate with real-book E2E (cover, TOC clickability, anchor jumps).
3. Keep legacy pipeline as fallback until repeated E2E sign-off.
