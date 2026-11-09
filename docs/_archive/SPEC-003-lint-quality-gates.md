---
specId: SPEC-003
title: Lint and Test Quality Gates
status: ✅ 已完成 (Completed)
priority: P1 - Core Feature
creationDate: 2026-03-16
lastUpdateDate: 2026-03-16
owner: Lei Peng (AI-Assisted)
relatedSpecs:
  - SPEC-001
  - SPEC-002
tags:
  - ci
  - lint
  - test
  - quality-gate
  - github-actions
---

# SPEC-003: Lint and Test Quality Gates

## 1. Goal

> Enforce a deterministic CI quality gate that fails fast on code-quality issues before tests run, so BookWeaver keeps a consistently mergeable main branch.

## 2. Problem Statement

Without an explicit quality-gate contract, style/lint regressions and test regressions can enter pull requests with inconsistent local verification. This increases review noise, slows delivery, and raises risk of unstable branch state.

BookWeaver needs one stable CI sequence and a clear blocking policy that contributors can reproduce locally.

## 3. CI Model (lint -> test)

**Chosen approach**: GitHub Actions workflow `lint-and-test` with ordered jobs:

1. `lint` job:
   - `uv run ruff check .`
   - `uv run ruff format --check .`
2. `test` job:
   - depends on `lint` (`needs: lint`)
   - runs `uv run pytest -q`

This keeps feedback fast: lint/format failures stop the pipeline before test execution.

## 4. Blocking Policy

- `lint-and-test` is a required quality gate for pushes and pull requests.
- Any `ruff check`, `ruff format --check`, or `pytest` failure is **blocking**.
- Contributors must fix failures before merge; bypass/ignore is not part of normal workflow.
- Local pre-PR verification should mirror CI commands to reduce failed runs in remote CI.

## 5. Acceptance Criteria

- [x] Workflow `lint-and-test` exists under `.github/workflows/lint.yml`.
- [x] CI execution order is lint first, test second (`needs: lint`).
- [x] Lint job runs both `ruff check` and `ruff format --check`.
- [x] Test job runs `uv run pytest -q`.
- [x] Contributor docs list local commands and explain blocking behavior.

## 6. Rollout Notes

- Existing workflow already enforces gate sequencing; this SPEC formalizes expected behavior.
- README and CLAUDE contributor notes must stay aligned with CI commands.
- If lint rules are tightened later, update both this SPEC and contributor docs in the same change.

## 7. Status History

| Date | Status | Note |
|------|--------|------|
| 2026-03-16 | ✅ 已完成 (Completed) | Captured and documented current lint-first CI quality gate |

## 8. Related

- **Workflow**: `.github/workflows/lint.yml`
- **Docs**: `README.md`, `CLAUDE.md`
- **Specs**: [SPEC-001](./SPEC-001-multi-tier-gemini-translation.md), [SPEC-002](./SPEC-002-prompt-model-stability.md)
