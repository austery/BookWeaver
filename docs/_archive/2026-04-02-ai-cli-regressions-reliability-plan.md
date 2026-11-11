# AI CLI Regressions & Reliability Plan (Execution Record)

Date: 2026-04-02  
Status: Implemented (core fixes complete), legacy removal deferred

## Goal

Stabilize the post-merge `ai.cli` runtime for CLI-first usage by fixing correctness surprises and restoring reliability features (resume + observability), then evaluate whether legacy pipeline scripts can be safely removed.

## Implemented high-priority fixes

1. Explicit model override semantics
   - `--model pro` now honors explicit alias resolution without silent downgrade via probe fallback.
2. CLI transient retry hardening
   - Improved retry budgeting/validation and clearer retry exhaustion error context.
3. Checkpoint resume restoration
   - Added `--resume`, `--force-resume`, and `--checkpoint-dir` support in `ai.cli`.
   - Checkpoint artifacts persisted under `.bookweaver_checkpoints/...` with compatibility checks.
4. Runtime progress observability
   - Added structured progress events (`model/input/resume/translate/source/batch/save/done/error`) for stage-localized diagnosis.
5. Glossary index detection pass-3
   - Added content-pattern heuristic for non-standard index docs (tail-spine, heading + line ratio guardrails).
6. Runtime CLI→API fallback semantics
   - `--cli-api-fallback` now switches only on transient/transport CLI translation failures.
   - Generic permanent CLI failures remain fail-fast.

## Legacy pipeline removal evaluation (Task 7)

Decision: **Do not remove legacy 01–09 pipeline scripts yet.**

Reasoning:
- PDF/DOCX end-to-end output rendering (steps 5–7 equivalents) is still shell-orchestrated and not fully absorbed into `ai.cli`.
- `translatebook.sh` remains the required path for non-EPUB full-format generation.
- Removing legacy scripts now would break active workflows and violate parity expectations.

Dependency gate for future removal:
- Complete SPEC-013 parity (sink-based rendering/export in `ai.cli` for markdown/PDF path).
- Verify parity checklist across EPUB + non-EPUB workflows (resume behavior, observability, output compatibility).
- Only then stage deprecation/removal.

## Verification gates used

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run tach check`
- `uv run pytest -q`
- `bash -n translatebook.sh`

## Follow-up backlog

1. Execute SPEC-013 to absorb output rendering/export into Python CLI path.
2. Re-run parity checklist with representative EPUB/PDF/DOCX books.
3. Stage legacy deprecation, then removal after parity sign-off.

