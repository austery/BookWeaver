---
specId: SPEC-004
title: Baoyu-Style Agent-Orchestrated Translation Workflow Evaluation
status: 🟡 Ready for Implementation
priority: P2 - Enhancement
creationDate: 2026-03-17
lastUpdateDate: 2026-03-17
owner: Lei Peng (AI-Assisted)
relatedSpecs:
  - SPEC-001
  - SPEC-002
  - SPEC-003
tags:
  - agent-orchestration
  - translation-quality
  - throughput
  - latency
  - prompt-assembly
  - evaluation
---

# SPEC-004: Baoyu-Style Agent-Orchestrated Translation Workflow Evaluation

## 1. Goal

Determine whether an optional Baoyu-style orchestrated workflow can deliver enough measurable quality gain to justify added latency and orchestration complexity, while preserving BookWeaver's current fast default path.

## 2. Background

BookWeaver currently runs a deterministic 7-step pipeline:

- Step 3 translates chunks (`output_pageXXXX.md`)
- Step 4 merges bilingual output (`output.md`)
- Step 5-7 render and export final formats

This path is stable and throughput-oriented, but prompt strategy is simpler than agent-oriented workflows.

`baoyu-translate` demonstrates a richer workflow with explicit artifacts and optional refinement loops:

- **Quick mode**: translate directly
- **Normal mode**: analysis -> prompt assembly (`02-prompt.md`) -> translate (chunked if needed)
- **Refined mode**: normal flow + critique -> revision -> polish

Primary concern: orchestration can become too slow for long books.

## 3. Design Decision

**Chosen approach**: Keep the current pipeline as default (`fast`) and add an explicitly opt-in `orchestrated` mode for evidence-based quality evaluation.

**Rationale**: This protects existing throughput and operational simplicity while enabling measurable quality experiments.

| Alternative | Pros | Cons | Decision |
|-------------|------|------|----------|
| A. Full replacement with refined workflow | Maximum quality controls and review loops | High latency and migration risk | ❌ Rejected |
| B. Optional orchestration on top of current flow | Balanced quality exploration with low risk | Dual-path maintenance | ✅ Chosen |
| C. Keep fast-only pipeline | Lowest complexity and runtime | No path to evaluate quality uplift | ❌ Rejected |

## 4. Architecture and Contracts

### 4.1 Workflow Mode Contract

Add a mode switch in translation entrypoint:

- `--workflow-mode fast` (default; current behavior unchanged)
- `--workflow-mode orchestrated` (new optional quality path)
- `--workflow-mode auto` (optional extension, not required for initial rollout)

Behavior rules:

- If user explicitly selects `orchestrated`, orchestration failures are terminal (no silent downgrade).
- `fast` remains zero-interaction and backward-compatible.
- Step 4-7 export chain remains unchanged and consumes the same translation-chunk contract.

### 4.2 Orchestrated Reference Stages

1. **Analysis stage**: produce `01-analysis.md` (tone, glossary, comprehension challenges)
2. **Prompt assembly stage**: produce shared `02-prompt.md`
3. **Translation stage**:
   - non-chunked: single pass
   - chunked: structured markdown chunking + parallel subagent drafts + ordered merge
4. **Refinement stage (optional)**:
   - `04-critique.md` (diagnosis)
   - `05-revision.md` (apply fixes)
   - `06-polish.md` (finalized translated output before chunk normalization)

### 4.3 Output Compatibility Contract

Both `fast` and `orchestrated` must emit Step 3 outputs in the same format:

- `output_pageXXXX.md` (translation-only chunk outputs)

This is required so Step 4 (`04_merge_md.py`) and Step 5-7 can remain unchanged.

### 4.4 Artifact Persistence Contract

Orchestration artifacts must be persisted under the current run temp directory:

- `orchestration/01-analysis.md`
- `orchestration/02-prompt.md`
- `orchestration/03-translation/` (chunk drafts and merge traces)
- Optional refined artifacts:
  - `orchestration/04-critique.md`
  - `orchestration/05-revision.md`
  - `orchestration/06-polish.md`
- `orchestration/metrics.json` (timing, request counts, and score breakdown)

## 5. Component Design

Planned component boundaries for implementation:

- `03_translate_md.py`: mode dispatch + shared context assembly
- `ai/orchestrator.py`: stage orchestration and sequencing
- `ai/artifacts.py`: artifact write/read conventions and trace metadata
- `ai/evaluation.py`: weighted quality scoring + benchmark aggregation
- `ai/mode_contract.py`: mode parsing and compatibility guards
- Reuse existing modules where possible:
  - `ai/gemini_provider.py`
  - `ai/model_selector.py`
  - model probe/fallback logic from SPEC-002 path

## 6. Evaluation Framework and Decision Gates

### 6.1 Quality Score Definition

Quality score is a weighted total (0-100):

- Terminology consistency: **40%**
- Fidelity to source meaning: **35%**
- Fluency/readability: **25%**

`weighted_quality = 0.40 * terminology + 0.35 * fidelity + 0.25 * fluency`

### 6.2 Benchmark Corpus

Use a fixed benchmark set:

- 3 representative books
- 30 chunks per book
- Same source chunks evaluated in both modes (`fast` vs `orchestrated`)

### 6.3 Gate 1 (Orchestrated Adoption Gate)

`orchestrated` passes Gate 1 only if both conditions are true:

- Weighted quality uplift is **>= +5 points** versus `fast`
- End-to-end runtime is **<= 2.0x** `fast`

### 6.4 Gate 2 (Refined Loop Adoption Gate)

`critique -> revision -> polish` is adopted only if Gate 1 already passes and refined loop shows net additional gain within acceptable runtime overhead.

Go/no-go must be explicitly recorded as:

- Adopt
- Partial adopt
- Defer

## 7. Error Handling and Observability

- No silent failure or hidden fallback when mode is explicitly selected.
- Failures must include stage name and actionable error context.
- Metrics and traces must be persisted to artifacts for reproducibility.
- Logs should include selected mode, model path, fallback path (if any), and per-stage timing.

## 8. Testing and Acceptance Strategy

### 8.1 Testing Layers

1. Unit tests:
   - mode dispatch behavior
   - artifact naming and persistence
   - weighted scoring computation
2. Integration tests:
   - both `fast` and `orchestrated` produce compatible `output_pageXXXX.md`
3. Regression tests:
   - Step 4-7 output chain remains unchanged
4. Benchmark tests:
   - latency/throughput/quality comparison report generation

### 8.2 Acceptance Criteria

- [ ] `fast` remains default and behavior-compatible with current pipeline.
- [ ] `orchestrated` is explicit opt-in and artifact-traceable.
- [ ] Step 3 output contract remains compatible with Step 4-7.
- [ ] Benchmark report includes weighted quality delta and runtime delta.
- [ ] Gate 1 and Gate 2 decisions are recorded with rationale.

## 9. Implementation Phases

### Phase 1: Contract and Mapping

- [ ] Define mode contract and compatibility matrix
- [ ] Map orchestrated artifacts to BookWeaver temp directory layout
- [ ] Confirm unchanged Step 4-7 consumption contract

### Phase 2: Orchestrated Normal-Flow POC

- [ ] Add analysis + prompt assembly + translation stages
- [ ] Keep fast mode as default
- [ ] Emit compatible `output_pageXXXX.md` outputs

### Phase 3: Evaluation and Gate Decisions

- [ ] Run benchmark corpus across both modes
- [ ] Apply Gate 1 (`+5` quality and `<= 2.0x` runtime)
- [ ] Apply Gate 2 for refined loop
- [ ] Publish explicit decision record

## 10. Status History

| Date | Status | Note |
|------|--------|------|
| 2026-03-17 | 📝 Draft | Initial draft created |
| 2026-03-17 | 🟡 Ready for Implementation | Design validated with explicit gates, contracts, and benchmark definition |

## 11. Related

- **Code**: `translatebook.sh`, `03_translate_md.py`, `04_merge_md.py`, `05_md_to_html.py`
- **Specs**: [SPEC-001](./SPEC-001-multi-tier-gemini-translation.md), [SPEC-002](./SPEC-002-prompt-model-stability.md), [SPEC-003](./SPEC-003-lint-quality-gates.md)
- **Design Doc**: `docs/plans/2026-03-17-baoyu-orchestrated-evaluation-design.md`
- **Reference**: `/Users/leipeng/Documents/Projects/baoyu-skills/skills/baoyu-translate/SKILL.md`
