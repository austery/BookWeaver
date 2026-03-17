# Baoyu-Orchestrated Translation Evaluation Design (BookWeaver)

Date: 2026-03-17

Status: Approved

## 1. Goal

Define an implementation-ready design to evaluate whether a Baoyu-style orchestrated translation workflow should be adopted in BookWeaver, without breaking the existing fast default pipeline.

Decision priority:

- Quality improvement must be measurable and material.
- Runtime overhead must stay bounded.
- Existing Step 4-7 export chain must remain compatible.

## 2. Context

Current BookWeaver flow is deterministic and stable:

- Step 3 emits translation-only chunks (`output_pageXXXX.md`)
- Step 4 merges bilingual markdown
- Step 5-7 generate output formats

The orchestrated reference introduces richer intermediate stages:

- Analysis (`01-analysis.md`)
- Prompt assembly (`02-prompt.md`)
- Translation (chunk or non-chunk)
- Optional refinement loop (`critique -> revision -> polish`)

The design requirement is not full replacement. It is controlled, evidence-driven comparison against the existing fast path.

## 3. Chosen Approach

Adopt a dual-path architecture:

- `fast` mode remains default and unchanged.
- `orchestrated` mode is explicit opt-in for quality evaluation.

Why this approach:

- Preserves current throughput for default users.
- Enables measurable quality experiments.
- Avoids risky all-at-once migration.

## 4. Architecture

### 4.1 Workflow Modes

Introduce mode contract at translation entrypoint:

- `--workflow-mode fast`
- `--workflow-mode orchestrated`
- Optional later extension: `--workflow-mode auto`

Behavior:

- Explicit `orchestrated` selection means orchestration-stage failures are terminal.
- No silent fallback in explicit mode.
- `fast` behavior remains backward-compatible.

### 4.2 Stage Flow

Orchestrated path:

1. Analysis stage
2. Prompt assembly stage
3. Translation stage
4. Optional refined stage (`critique`, `revision`, `polish`)
5. Normalize outputs into Step 3 compatibility contract

Compatibility requirement:

- Both modes must emit the same `output_pageXXXX.md` contract for downstream steps.

### 4.3 Artifact Persistence

Persist artifacts under run temp directory:

- `orchestration/01-analysis.md`
- `orchestration/02-prompt.md`
- `orchestration/03-translation/*`
- `orchestration/04-critique.md` (optional)
- `orchestration/05-revision.md` (optional)
- `orchestration/06-polish.md` (optional)
- `orchestration/metrics.json`

`metrics.json` includes per-stage timing, model path, fallback path, and score breakdown.

## 5. Component Boundaries

New modules:

- `ai/orchestrator.py`: orchestrates stage sequencing and retries
- `ai/artifacts.py`: standardized artifact write/read and trace metadata
- `ai/evaluation.py`: weighted quality scoring and benchmark summaries
- `ai/mode_contract.py`: mode parsing and runtime guardrails

Changed entrypoint:

- `03_translate_md.py` dispatches mode and assembles shared context.

Reused modules:

- `ai/gemini_provider.py`
- `ai/model_selector.py`
- probe/fallback behavior established in SPEC-002

## 6. Evaluation Design

### 6.1 Weighted Quality Score

Use 0-100 weighted total:

- Terminology consistency: 40%
- Fidelity: 35%
- Fluency: 25%

Formula:

`weighted_quality = 0.40 * terminology + 0.35 * fidelity + 0.25 * fluency`

### 6.2 Benchmark Corpus

Fixed benchmark set:

- 3 representative books
- 30 chunks per book
- Same chunk set compared across `fast` and `orchestrated`

### 6.3 Decision Gates

Gate 1 (orchestrated adoption):

- Quality uplift >= +5 points versus `fast`
- End-to-end runtime <= 2.0x `fast`

Gate 2 (refined loop adoption):

- Evaluated only after Gate 1 passes
- Refined loop must show net additional quality gain within acceptable runtime overhead

Decision outcomes:

- Adopt
- Partial adopt
- Defer

## 7. Error Handling and Observability

- No silent fail-open behavior for explicit orchestrated mode.
- Every failure includes stage name and actionable context.
- All stage artifacts and metrics are persisted for auditability and reproducibility.
- Logs must report active mode, selected model, fallback chain (if used), and stage timings.

## 8. Testing Strategy

Unit:

- Mode dispatch rules
- Artifact naming and persistence
- Weighted scoring correctness

Integration:

- `fast` and `orchestrated` produce compatible chunk outputs

Regression:

- Step 4-7 behavior unchanged

Benchmark:

- Generate machine-readable and human-readable comparison report for latency, throughput, and quality

## 9. Scope Boundaries

In scope:

- Mode contract
- Orchestrated normal-flow POC
- Artifact persistence
- Benchmark and gate decisions

Out of scope (this iteration):

- Mandatory replacement of fast mode
- Autonomous online self-tuning orchestration policies

## 10. Rollout Plan

1. Contract and compatibility mapping
2. Orchestrated normal-flow POC
3. Benchmark run and Gate 1 decision
4. Refined loop trial and Gate 2 decision
5. Record final adoption decision
