# EPUB Baoyu-Normal Alignment Design

## Goal

Align BookWeaver EPUB context pass with **Baoyu normal mode** workflow semantics, so generated artifacts are not simplified placeholders but reusable translation-control assets.

Target workflow:

1. Extract representative source context from EPUB (`TOC + Preface/Introduction + Chapter 1`)
2. Analyze sampled content with Baoyu-normal structure (`01-analysis.md`)
3. Resolve translation presets (`audience`, `style`) automatically by book signals
4. Materialize `02-prompt.md` from Baoyu template sections
5. Reuse `02-prompt.md` as shared prompt for full-book translation

## Why this change

Current EPUB context artifacts are structurally insufficient:

- `01-analysis.md` is only a sample dump, not a translation analysis document
- `02-prompt.md` lacks Baoyu template sections and preset semantics
- Audience/style are neither auto-inferred nor explicitly traceable

This causes mismatch with user expectations and breaks the core value of Baoyu normal mode: **analysis-first, file-based prompt control, reusable workflow memory**.

## Scope

### In scope

- EPUB workflow (`--workflow epub` / `--epub-translate-roundtrip`) only
- Replace current simplified `01-analysis.md` / `02-prompt.md` format with Baoyu-normal-compatible format
- Add auto preset resolution for:
  - Audience: `general | technical | academic | business`
  - Style: `storytelling | formal | technical | literal | academic | business | humorous | conversational | elegant`
- Add explicit override support via CLI flags:
  - `--audience`
  - `--style`
- Persist preset decision + rationale into `01-analysis.md`
- Ensure `02-prompt.md` is assembled by fixed template sections and used in translation pass

### Out of scope

- Refined-mode critique/revision/polish chain (`03/04/05`) for EPUB path
- Replacing markdown Step3 pipeline in this iteration
- Multi-agent chunk orchestration in EPUB path (future enhancement)

## Contract and CLI behavior

### Effective preset resolution (deterministic)

1. If `--audience` provided, use it; else run auto audience inference
2. If `--style` provided, use it; else run auto style inference
3. Record both final values and reasoning in `01-analysis.md`

### Auto inference principles

- Detect domain/style signals from sampled context (terminology density, discourse style, rhetorical patterns)
- Map signals to nearest preset
- Prefer conservative mapping (avoid overfitting to niche labels)

### Artifact contract

Under `<temp_dir>/epub_orchestration/`:

- `01-analysis.md` (Baoyu structured sections)
- `02-prompt.md` (Baoyu template sections)
- `context_manifest.json` (selection/sampling/signature metadata)

## `01-analysis.md` required structure

Must include exactly these logical sections (names can follow current markdown conventions but semantics must match):

1. Quick Summary
2. Core Content
3. Background Context
4. Terminology
5. Tone & Style
6. Comprehension Challenges
7. Figurative Language & Metaphor Mapping
8. Structural & Creative Challenges
9. Preset Resolution
   - audience (value + reason)
   - style (value + reason)
   - whether overridden by CLI

## `02-prompt.md` required structure

Assemble from Baoyu subagent template semantics:

1. Target Audience (resolved description)
2. Translation Style (resolved style description)
3. Content Background (inlined from analysis)
4. Glossary (merged built-in + extracted terms)
5. Comprehension Challenges (note policy inputs)
6. Translation Principles (Baoyu-compatible rule set)

No ad-hoc freeform prompt body. Section contract must remain stable for manual editing and rerun.

## Data flow

1. Select context docs (existing heuristic)
2. Sample paragraphs (existing budget logic)
3. Build analysis model from sampled text
4. Resolve presets (auto + override)
5. Render `01-analysis.md`
6. Render `02-prompt.md` from template sections
7. Hash prompt and write manifest
8. Translation pass uses rendered prompt

## Error handling

- If context extraction yields zero usable text, fail with explicit error
- If auto inference cannot classify confidently, fallback to:
  - audience=`general`
  - style=`storytelling`
  and record fallback reason in analysis
- Invalid CLI preset value must fail fast (argparse choices for known presets)

## Testing strategy

1. Unit tests for preset inference mapping
2. Unit tests for CLI override precedence over auto inference
3. Unit tests for required analysis sections existence
4. Unit tests for required prompt sections existence
5. Regression tests verifying translation pass uses generated `02-prompt.md`
6. Checkpoint compatibility tests remain green

## Acceptance criteria

1. Roman Emperor EPUB generated `01-analysis.md` contains preset resolution and full Baoyu analysis sections
2. Roman Emperor EPUB generated `02-prompt.md` contains all required template sections
3. Auto inference classifies Roman Emperor as non-technical style/audience appropriately (unless overridden)
4. For technical sample content, inference can resolve to technical audience/style where signals are clear
5. CLI override always wins and is explicitly recorded in analysis
6. Existing quality gates pass (`ruff`, `ruff format --check`, `pytest -q`, `bash -n translatebook.sh`)

## Risks and mitigations

- Risk: Heuristic preset inference unstable across books
  - Mitigation: deterministic feature thresholds + rationale logging
- Risk: Prompt section bloat reduces model performance
  - Mitigation: cap excerpt verbosity, keep structured concise sections
- Risk: Drift from Baoyu template over time
  - Mitigation: section-presence tests as contract tests

## Next step

Create implementation plan with TDD-first tasks (preset model, analysis renderer, prompt renderer, integration wiring, verification).
