# Dynamic Prompt + Refined Loop Minimal Evaluation Design

Date: 2026-03-21
Project: BookWeaver
Status: Approved

## 1. Decision Summary

Proceed with dynamic prompt idea, but only as a **minimal gated experiment** first.

Chosen scope:

- Compare `fast` vs `orchestrated(normal+refined)` on a small fixed corpus
- Keep BookWeaver current production path unchanged
- Promote only if quality/time gates pass

This is an evaluation project, not a default workflow migration.

## 2. Current State and Gap

From `feature/spec004-agent-eval-wip`:

- Implemented: workflow mode contract and Step-3 mode argument wiring
- Not implemented yet: orchestrated runtime core
  - `ai/orchestrator.py`
  - `ai/artifacts.py`
  - `ai/evaluation.py`

Therefore the branch is **foundation-only**, not yet capable of real quality gate evaluation.

## 3. Why This Direction

Dynamic prompt + refined loop can improve translation quality on difficult chapters, but carries obvious latency and complexity risks.

A minimal gated experiment gives:

- measurable evidence before high-cost rollout
- lower engineering risk than full replacement
- clear stop conditions if gains are insufficient

## 4. Experiment Scope (Minimal)

### 4.1 In Scope

1. Implement orchestrated evaluation path for Step 3 only
2. Generate and persist artifacts:
   - `orchestration/01-analysis.md`
   - `orchestration/02-prompt.md`
   - `orchestration/03-translation/*`
   - `orchestration/04-critique.md`
   - `orchestration/05-revision.md`
   - `orchestration/06-polish.md`
   - `orchestration/metrics.json`
3. Run A/B benchmark on one representative book with 30 chunks:
   - A: `fast`
   - B: `orchestrated(normal+refined)`

### 4.2 Out of Scope

1. Changing default workflow
2. Enabling orchestrated path in mainline CLI by default
3. Multi-book full-scale benchmark
4. Autonomous online self-tuning or policy loops

## 5. Success Gates (Confirmed)

Adoption gate (must satisfy both):

1. Weighted quality uplift `>= +5` vs `fast`
2. End-to-end runtime `<= 2.0x` vs `fast`

If either fails: mark as `defer` and keep current fast-first production strategy.

## 6. Architecture (Evaluation Path)

## 6.1 Dispatch contract

- `--workflow-mode fast` (baseline)
- `--workflow-mode orchestrated` (experiment path)

No silent downgrade in explicit orchestrated mode.

### 6.2 Stage sequence

1. Analysis
2. Prompt assembly (dynamic prompt materialization to `02-prompt.md`)
3. Draft translation
4. Critique
5. Revision
6. Polish
7. Normalize output to Step-3 contract (`output_pageXXXX.md`)

### 6.3 Compatibility requirement

Downstream Step 4-7 must remain unchanged and consume standard Step-3 outputs.

## 7. Error Handling and Observability

1. Fail-fast for explicit orchestrated mode
2. Every stage logs with stage name and actionable context
3. Persist metrics and traces to artifacts for reproducibility
4. Record model selection and fallback path in metrics

## 8. Test and Benchmark Strategy

### 8.1 Code-level tests

1. Unit:
   - mode dispatch correctness
   - artifact write/read contract
   - weighted score formula correctness
2. Integration:
   - both modes produce compatible `output_pageXXXX.md`
3. Regression:
   - Step 4-7 unchanged behavior

### 8.2 Benchmark run

Fixed protocol:

- 1 book, 30 chunks, same chunk set for both modes
- collect:
  - terminology score
  - fidelity score
  - fluency score
  - weighted total
  - runtime ratio

Final output:

- explicit decision: `adopt` | `partial adopt` | `defer`
- rationale attached to measured metrics

## 9. Recommendation

Recommended execution order:

1. Finish minimal orchestrated runtime in `feature/spec004-agent-eval-wip`
2. Run single-book benchmark and gate decision
3. Only if gate passes, discuss broader rollout and branch integration

This keeps your current production momentum while validating whether the dynamic prompt idea truly earns its cost.
