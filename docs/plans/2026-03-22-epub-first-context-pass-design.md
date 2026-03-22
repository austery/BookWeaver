# EPUB-First Context Pass Design (Main Branch Path)

## Goal

Upgrade `--epub-translate-roundtrip` to an EPUB-first, analysis-driven prompt workflow that does **not** depend on Markdown chunk path.

The translation path should:

1. Extract global book context from sampled EPUB docs (`TOC + Preface + Chapter 1`).
2. Build shared context artifacts (`01-analysis.md`, `02-prompt.md`).
3. Reuse the shared prompt for all spine document translations.

## Why this design

Current system has multiple prompt sources:

- Markdown Step3 profile templates (`config/prompts/*.txt`)
- EPUB immersive inline templates (`_IMMERSIVE_*` in `ai/epub_translate_roundtrip.py`)
- Orchestrated prompt modules (`ai/orchestration_*`)

This causes drift and inconsistent translation behavior. User requirement is clear: EPUB package path should be primary, and context can be inferred from a representative subset (preface/ch1) rather than full-book pre-analysis.

## Scope

### In scope (Iteration 1)

- Modify **main branch EPUB roundtrip path only**.
- Add pre-translation Context Pass in `ai/epub_translate_roundtrip.py`.
- Sample docs for context: **TOC + Preface + Chapter 1**.
- Sampling budget:
  - max 8 paragraphs per sampled doc
  - max 120 paragraphs total
- Generate artifacts under temp output:
  - `epub_orchestration/01-analysis.md`
  - `epub_orchestration/02-prompt.md`
  - `epub_orchestration/context_manifest.json`
- Use generated `02-prompt.md` for whole-book translation.
- Keep default model behavior Flash-compatible.

### Out of scope (Iteration 1)

- Rewriting Markdown Step3 prompt stack.
- Full prompt-source unification migration (tracked separately as TODO `consolidate-prompt-sources`).
- Multi-model optimization heuristics beyond current defaults.

## High-Level Architecture

### Existing path

`09_epub_translate_roundtrip.py` -> `run_translate_roundtrip(...)` -> per-spine translation with `_create_translation_prompt(...)`.

### New path

`run_translate_roundtrip(...)` becomes:

1. Load package + spine docs as today.
2. Run **Context Pass**:
   - pick sample docs from spine/manifest candidates
   - extract representative segments with budget
   - produce analysis and prompt artifacts
3. Translation Pass:
   - use shared prompt text from `02-prompt.md`
   - translate each spine doc segments using same prompt
4. Preserve checkpoint/repack behavior.

## Data Flow and Artifact Locations

For source EPUB temp directory (existing roundtrip temp workspace):

- `epub_orchestration/01-analysis.md`
- `epub_orchestration/02-prompt.md`
- `epub_orchestration/context_manifest.json`

`context_manifest.json` records:

- selected docs (`toc/preface/ch1` resolution result)
- sampled paragraph counts per doc
- total paragraph count
- context signature/hash
- prompt hash

Translation pass reads `02-prompt.md` and appends optional `-p/--prompt` extra instructions.

## Sampling Strategy

### Doc selection priority

1. TOC-like document (nav/toc manifest hints)
2. Preface-like document (filename/title heuristics: preface/introduction/foreword/prologue)
3. First chapter from spine reading order (first content doc after front matter)

If a category is missing, continue with available docs; never block solely for missing preface.

### Segment budget rules

- Per selected doc: max 8 paragraphs
- Global max: 120 paragraphs
- Preserve original order (spine/document order) for context coherence

## Prompt Construction

Use existing orchestrated modules to avoid re-inventing:

- context loader (`ai/orchestration_context.py`)
- analysis builder (`ai/orchestration_analysis.py`)
- prompt assembler (`ai/orchestration_prompt.py`)

For EPUB context pass:

- Input text source is EPUB sampled segments (not markdown pages).
- Output format remains analysis/prompt markdown artifacts.
- Shared prompt must include:
  - audience/style
  - content background
  - glossary
  - comprehension challenges
  - translation principles

## Failure Strategy and Checkpoint Compatibility

### Failure policy

1. Context Pass failure -> fail fast, do not start translation pass.
2. Translation pass -> doc-level retries, collect failed docs, report summary at end.

### Checkpoint compatibility

Checkpoint state version bump and additional keys:

- `context_signature`
- `prompt_hash`

Resume policy:

- if signature/hash mismatch: force context rebuild and reject stale checkpoint docs unless user opts to rebuild via explicit flag.
- support old checkpoint version read path for backward compatibility.

Potential CLI extension:

- `--force-context-rebuild` for deterministic cache invalidation.

## Testing and Acceptance

### Unit tests

- sample doc selector picks TOC/Preface/Ch1 correctly
- sampling budget enforcement (8 per doc, 120 total)
- context signature stability
- prompt assembly contains required sections

### Integration tests

- context pass generates `01/02/manifest`
- roundtrip translation uses generated prompt artifact
- checkpoint mismatch triggers rebuild behavior

### Regression

- Existing `--epub-translate-roundtrip` behavior remains backward-compatible when new options are not set.

### Acceptance criteria

1. Real EPUB run creates `epub_orchestration/01-analysis.md`, `02-prompt.md`, `context_manifest.json`.
2. Translation pass completes using shared prompt artifact.
3. Full quality gates pass (`ruff`, `pytest`, shell check).
4. No dependency on Markdown chunk pipeline.

## Open follow-up TODO

- `consolidate-prompt-sources`: design unified prompt architecture across Markdown fast, EPUB immersive, and orchestrated paths.
