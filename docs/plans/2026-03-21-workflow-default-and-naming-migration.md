# Workflow Default and Naming Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make EPUB package-preserving workflow the default for EPUB input, keep Markdown workflow for non-EPUB/legacy use, and migrate user-facing naming to `--workflow epub|markdown`.

**Architecture:** Introduce a single workflow resolver in `translatebook.sh` that computes effective workflow from input extension + explicit override. Keep backward compatibility by mapping old flags to the new workflow contract with deprecation warnings. Update README/help text to make defaults and mode selection unambiguous and reduce misuse.

**Tech Stack:** Bash (`translatebook.sh`), Python/pytest (`tests/unit/*`), existing BookWeaver scripts (`09_epub_translate_roundtrip.py`, `03_translate_md.py`), `uv` quality gates.

---

### Task 1: Add failing tests for workflow contract

**Files:**
- Create: `tests/unit/test_translatebook_workflow_mode.py`
- Modify: `tests/unit/test_epub_baseline_cli.py`
- Test: `tests/unit/test_translatebook_workflow_mode.py`
- Test: `tests/unit/test_epub_baseline_cli.py`

**Step 1: Write failing resolver tests**

```python
from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "translatebook.sh"


def _resolve_workflow(input_file: str, workflow: str = "") -> str:
    command = (
        f'source "{SCRIPT_PATH}" >/dev/null; '
        f'resolve_workflow_for_input "{input_file}" "{workflow}"'
    )
    completed = subprocess.run(
        ["bash", "-lc", command],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def test_epub_defaults_to_epub_workflow() -> None:
    assert _resolve_workflow("book.epub") == "epub"


def test_pdf_defaults_to_markdown_workflow() -> None:
    assert _resolve_workflow("book.pdf") == "markdown"


def test_explicit_markdown_override_for_epub() -> None:
    assert _resolve_workflow("book.epub", "markdown") == "markdown"
```

**Step 2: Extend CLI contract tests (expected to fail initially)**

```python
def test_translatebook_help_includes_workflow_option() -> None:
    content = Path("translatebook.sh").read_text(encoding="utf-8")
    assert "--workflow" in content
```

**Step 3: Run tests to verify fail**

Run: `uv run pytest -q tests/unit/test_translatebook_workflow_mode.py tests/unit/test_epub_baseline_cli.py -k workflow -v`  
Expected: FAIL (function/flag missing).

**Step 4: Keep red baseline commit**

```bash
git add tests/unit/test_translatebook_workflow_mode.py tests/unit/test_epub_baseline_cli.py
git commit -m "test: add failing workflow mode contract checks"
```

### Task 2: Implement workflow resolver and CLI parsing

**Files:**
- Modify: `translatebook.sh`
- Test: `tests/unit/test_translatebook_workflow_mode.py`
- Test: `tests/unit/test_epub_baseline_cli.py`

**Step 1: Implement resolver and new CLI option**

```bash
# New defaults
WORKFLOW_OVERRIDE=""
RESOLVED_WORKFLOW=""

# Help
--workflow MODE        Workflow mode: epub|markdown (default: auto by input type)

# Parse args
--workflow)
    WORKFLOW_OVERRIDE="$2"
    shift 2
    ;;
```

```bash
resolve_workflow_for_input() {
    local input_file="$1"
    local workflow_override="${2:-}"
    if [[ -n "$workflow_override" ]]; then
        echo "$workflow_override"
        return 0
    fi
    if is_epub_file "$input_file"; then
        echo "epub"
    else
        echo "markdown"
    fi
}
```

**Step 2: Validate `--workflow` value**

```bash
if [[ -n "$WORKFLOW_OVERRIDE" ]] && [[ ! "$WORKFLOW_OVERRIDE" =~ ^(epub|markdown)$ ]]; then
    log_error "Invalid workflow: $WORKFLOW_OVERRIDE (must be epub|markdown)"
    exit 2
fi
```

**Step 3: Compute resolved workflow in `main`**

```bash
RESOLVED_WORKFLOW="$(resolve_workflow_for_input "$INPUT_FILE" "$WORKFLOW_OVERRIDE")"
```

**Step 4: Show resolved workflow in config output**

```bash
echo "  Workflow override: ${WORKFLOW_OVERRIDE:-auto}"
echo "  Resolved workflow: ${RESOLVED_WORKFLOW}"
```

**Step 5: Run tests**

Run: `uv run pytest -q tests/unit/test_translatebook_workflow_mode.py tests/unit/test_epub_baseline_cli.py -k workflow -v`  
Expected: PASS.

**Step 6: Commit**

```bash
git add translatebook.sh tests/unit/test_translatebook_workflow_mode.py tests/unit/test_epub_baseline_cli.py
git commit -m "feat: add workflow resolver and workflow cli option"
```

### Task 3: Rewire execution path to resolved workflow

**Files:**
- Modify: `translatebook.sh`
- Modify: `tests/unit/test_epub_baseline_cli.py`
- Test: `tests/unit/test_epub_baseline_cli.py`

**Step 1: Add failing dry-run behavior tests**

```python
def test_epub_default_dry_run_uses_epub_workflow() -> None:
    # run with --dry-run and .epub input
    # assert output includes "Resolved workflow: epub"
    # assert output includes "[STEP workflow-epub]"
    ...
```

**Step 2: Implement branch by `RESOLVED_WORKFLOW`**

- Keep baseline mode (`--epub-baseline`) as independent early-exit path.
- Replace direct `if [[ "$EPUB_TRANSLATE_ROUNDTRIP" == true ]]` branch with:

```bash
if [[ "$RESOLVED_WORKFLOW" == "epub" ]]; then
    log_step "workflow-epub" "EPUB package-preserving translation workflow"
    # call 09_epub_translate_roundtrip.py (existing implementation)
    exit 0
fi
```

- Markdown path remains existing step 1-7 pipeline and is only entered when `RESOLVED_WORKFLOW=markdown`.

**Step 3: Rename user-facing log text**

- `translate roundtrip` -> `EPUB package-preserving workflow` in config/help/dry-run messaging.

**Step 4: Run behavior tests**

Run: `uv run pytest -q tests/unit/test_epub_baseline_cli.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add translatebook.sh tests/unit/test_epub_baseline_cli.py
git commit -m "feat: default epub inputs to package-preserving workflow"
```

### Task 4: Backward compatibility for old flags with deprecation warnings

**Files:**
- Modify: `translatebook.sh`
- Create: `tests/unit/test_translatebook_flag_compat.py`
- Test: `tests/unit/test_translatebook_flag_compat.py`

**Step 1: Add failing compatibility tests**

```python
def test_old_translate_roundtrip_flag_maps_to_epub_workflow() -> None:
    # dry-run with --epub-translate-roundtrip should resolve to epub workflow
    # and emit deprecation warning
    ...
```

```python
def test_conflicting_workflow_and_old_flag_fails() -> None:
    # --workflow markdown + --epub-translate-roundtrip -> exit 2
    ...
```

**Step 2: Implement compatibility mapping**

- `--epub-translate-roundtrip`:
  - set `WORKFLOW_OVERRIDE=epub`
  - print deprecation warning suggesting `--workflow epub`
- keep `--epub-baseline` as-is (separate baseline mode).
- add conflict detection when old/new options disagree.

**Step 3: Run compatibility tests**

Run: `uv run pytest -q tests/unit/test_translatebook_flag_compat.py -v`  
Expected: PASS.

**Step 4: Commit**

```bash
git add translatebook.sh tests/unit/test_translatebook_flag_compat.py
git commit -m "feat: add deprecated flag mapping to workflow option"
```

### Task 5: Rewrite README and help text for clarity

**Files:**
- Modify: `README.md`
- Modify: `translatebook.sh` (help text section)
- Optional modify (if referenced): `CLAUDE.md`

**Step 1: Add README mode matrix**

Add top section table:

| Input | Goal | Recommended workflow | Command |
|------|------|----------------------|---------|
| EPUB | Preserve structure/nav fidelity | `epub` | `./translatebook.sh --workflow epub ...` |
| PDF/DOCX | Convert and translate | `markdown` | `./translatebook.sh --workflow markdown ...` |

**Step 2: Add migration mapping table**

- `--epub-translate-roundtrip` -> `--workflow epub` (deprecated alias)
- default behavior statement:
  - EPUB default: `epub`
  - non-EPUB default: `markdown`

**Step 3: Replace user-facing `roundtrip` wording**

Use:
- `EPUB package-preserving workflow`
- `Markdown conversion workflow`

Keep historical/spec references only where needed.

**Step 4: Validate docs changes**

Run:

```bash
rg -n "workflow|package-preserving|epub-translate-roundtrip|deprecated" README.md translatebook.sh
```

Expected: updated wording and mapping present.

**Step 5: Commit**

```bash
git add README.md translatebook.sh CLAUDE.md
git commit -m "docs: clarify workflow defaults and naming migration"
```

### Task 6: Full verification and release readiness checks

**Files:**
- Verify changed files only

**Step 1: Run repository quality gates**

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
bash -n translatebook.sh
```

Expected: all pass.

**Step 2: Run CLI sanity checks**

```bash
./translatebook.sh --dry-run --workflow epub tmp/Psycho-Cybernetics.epub
./translatebook.sh --dry-run --workflow markdown tmp/Psycho-Cybernetics.epub
./translatebook.sh --dry-run --epub-translate-roundtrip tmp/Psycho-Cybernetics.epub
```

Expected:
- first resolves `epub`,
- second resolves `markdown`,
- third resolves `epub` with deprecation warning.

**Step 3: Final commit if needed**

```bash
git add -A
git commit -m "chore: finalize workflow default migration verification"
```

**Step 4: Prepare PR summary**

Include:
- What changed in CLI behavior
- Why markdown is retained
- Deprecation window and migration path
