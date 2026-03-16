# Lint & Test Quality Gates Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Ruff lint checks and a serialized GitHub Actions gate (`lint -> test`) that blocks merges on failure.

**Architecture:** Use Ruff as a lightweight, repo-wide quality gate configured in `pyproject.toml`. Add a dedicated CI workflow that runs lint first, then unit tests only if lint passes. Capture policy in a new spec so behavior is explicit and auditable.

**Tech Stack:** Python 3.13, uv, Ruff, pytest, GitHub Actions

---

### Task 1: Add failing quality-gate tests

**Files:**
- Create: `tests/unit/test_quality_gates.py`
- Test: `tests/unit/test_quality_gates.py`

**Step 1: Write the failing test**

```python
from __future__ import annotations

import tomllib
from pathlib import Path


def test_pyproject_has_ruff_dev_dependency():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dev_deps = pyproject["dependency-groups"]["dev"]
    assert any(dep.startswith("ruff") for dep in dev_deps)


def test_ci_workflow_has_serial_lint_then_test():
    workflow = Path(".github/workflows/lint.yml").read_text(encoding="utf-8")
    assert "name: lint-and-test" in workflow
    assert "ruff check ." in workflow
    assert "ruff format --check ." in workflow
    assert "uv run pytest -q" in workflow
    assert "needs: lint" in workflow
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_quality_gates.py -v`  
Expected: FAIL because Ruff dependency and workflow file are not present yet.

**Step 3: Write minimal implementation**

No implementation in this task. Keep tests failing first.

**Step 4: Re-run to confirm failure remains expected**

Run: `uv run pytest -q tests/unit/test_quality_gates.py -v`  
Expected: FAIL (same reasons as Step 2).

**Step 5: Commit**

```bash
git add tests/unit/test_quality_gates.py
git commit -m "test: add failing quality gate checks"
```

### Task 2: Implement Ruff config and CI workflow

**Files:**
- Modify: `pyproject.toml`
- Create: `.github/workflows/lint.yml`
- Test: `tests/unit/test_quality_gates.py`

**Step 1: Write the failing test (if not already committed)**

Use the tests from Task 1.

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_quality_gates.py -v`  
Expected: FAIL.

**Step 3: Write minimal implementation**

`pyproject.toml` (example shape):

```toml
[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "ruff>=0.12.0",
]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I"]
```

`.github/workflows/lint.yml`:

```yaml
name: lint-and-test
on:
  push:
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen --group dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .

  test:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen --group dev
      - run: uv run pytest -q
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/unit/test_quality_gates.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add pyproject.toml .github/workflows/lint.yml tests/unit/test_quality_gates.py uv.lock
git commit -m "feat(ci): add ruff lint and serialized test gate"
```

### Task 3: Add standalone spec for CI quality gates

**Files:**
- Create: `docs/architecture/specs/SPEC-003-lint-quality-gates.md`
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Step 1: Write documentation checks (manual)**

Checklist:
- New SPEC exists with Goal/Scope/Acceptance sections.
- README includes local lint commands.
- CLAUDE.md dev verification includes Ruff commands.

**Step 2: Verify current state fails checklist**

Run: `rg -n "ruff|SPEC-003|lint-and-test" README.md CLAUDE.md docs/architecture/specs`  
Expected: Missing SPEC-003 and missing lint command references.

**Step 3: Write minimal implementation**

Add `SPEC-003` covering:
- Problem statement
- Chosen CI model (`lint -> test`)
- Blocking policy
- Acceptance criteria

Update docs with:
- `uv run ruff check .`
- `uv run ruff format --check .`
- CI gate behavior summary

**Step 4: Re-run checks**

Run: `rg -n "ruff|SPEC-003|lint-and-test" README.md CLAUDE.md docs/architecture/specs`  
Expected: Matches found in all target docs.

**Step 5: Commit**

```bash
git add docs/architecture/specs/SPEC-003-lint-quality-gates.md README.md CLAUDE.md
git commit -m "docs(spec): add SPEC-003 for lint and test quality gates"
```

### Task 4: Full verification and final branch update

**Files:**
- Verify only: `.github/workflows/lint.yml`, `pyproject.toml`, `tests/unit/test_quality_gates.py`, docs

**Step 1: Run full validation**

Run:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
bash -n translatebook.sh
uv run python -m py_compile 03_translate_md.py ai/gemini_provider.py ai/model_probe.py 05_md_to_html.py 07_generate_formats.py
```

Expected:
- All checks pass
- No syntax regressions

**Step 2: Review diff scope**

Run: `git --no-pager status --short && git --no-pager diff --stat`  
Expected: only intended lint/spec/doc files plus `uv.lock`.

**Step 3: Final commit (if any remaining changes)**

```bash
git add -A
git commit -m "chore: finalize lint quality gates rollout"
```

**Step 4: Push and update PR**

```bash
git push
```

**Step 5: Request review**

Use `@superpowers:requesting-code-review` before merge.

