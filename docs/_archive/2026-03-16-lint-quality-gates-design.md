# Lint & Test Quality Gates Design

Date: 2026-03-16

Status: Approved

## 1. Goal

Add enforceable quality gates for Python code style and static lint checks, and run unit tests in CI before merge.

## 2. Scope

In scope:
- Ruff-based lint checks (`ruff check .`)
- Ruff formatting checks (`ruff format --check .`)
- CI pipeline with serialized jobs: `lint` then `test`
- Unit test job command: `uv run pytest -q`
- Contributor docs updates for local verification commands
- New architecture spec documenting lint/test CI gate policy

Out of scope:
- Type-checking via mypy
- Multi-platform CI matrix
- Auto-formatting in CI (check-only mode for now)

## 3. Chosen Approach

Selected: **Ruff + GitHub Actions serial gate (`lint -> test`)**

Why:
- Lightweight and fast for script-heavy Python repo
- Low config overhead and strong defaults
- Clear merge gate semantics: fail fast on lint, then validate behavior with tests

## 4. Design

## 4.1 Tooling

- Add Ruff to dev dependencies in `pyproject.toml`
- Add `[tool.ruff]` minimal configuration aligned with repository conventions

## 4.2 Local Workflow

Use the following commands locally:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

These commands become the canonical pre-PR verification flow.

## 4.3 CI Workflow

Create `.github/workflows/lint.yml` with:

1. Trigger: `push`, `pull_request`
2. Job `lint`
   - checkout
   - setup python + uv
   - `uv sync --frozen --group dev`
   - `uv run ruff check .`
   - `uv run ruff format --check .`
3. Job `test` depends on `lint`
   - `uv run pytest -q`

Policy:
- Any lint/test failure blocks PR merge.

## 4.4 Spec Update

Add new spec:
- `docs/architecture/specs/SPEC-003-lint-quality-gates.md`

The spec records:
- Problem statement
- CI gate design
- Acceptance criteria
- Rollout plan

## 5. Error Handling

- Keep checks explicit and fail loudly (non-zero exit)
- No silent fallback in CI
- Preserve full command output for troubleshooting

## 6. Testing & Acceptance

Acceptance criteria:
- `uv run ruff check .` passes locally
- `uv run ruff format --check .` passes locally
- `uv run pytest -q` passes locally
- CI runs serialized `lint -> test`
- PR is blocked when lint/test fails

