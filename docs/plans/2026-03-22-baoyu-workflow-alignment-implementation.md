# Baoyu Workflow Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild orchestrated mode so it follows baoyu’s analysis-driven prompt workflow, supports prompt-only artifacts, and keeps Flash as default.

**Architecture:** Add a small orchestration pipeline: context loading (preferences/glossary) -> analysis artifact -> rich prompt artifact -> optional translation stage. Keep fast mode unchanged. Implement phase gating in Step3 so `prompt-only` generates artifacts without translation.

**Tech Stack:** Python 3.12, pytest, ruff, Gemini CLI (`ai/gemini_provider.py`), existing BookWeaver Step3 pipeline.

---

### Task 1: Add Orchestrated Phase CLI Contract

**Files:**
- Modify: `03_translate_md.py`
- Test: `tests/unit/test_translate_step3_refactor.py`

**Step 1: Write the failing test**

```python
def test_step3_parse_arguments_accepts_orchestrated_phase(monkeypatch):
    ...
    assert args.orchestrated_phase == "prompt-only"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_translate_step3_refactor.py::test_step3_parse_arguments_accepts_orchestrated_phase`
Expected: FAIL (`orchestrated_phase` missing).

**Step 3: Write minimal implementation**

```python
parser.add_argument(
    "--orchestrated-phase",
    default="translate",
    choices=["prompt-only", "translate"],
)
```

Wire it into `translate_markdown_files(...)`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_translate_step3_refactor.py::test_step3_parse_arguments_accepts_orchestrated_phase`
Expected: PASS.

**Step 5: Commit**

```bash
git add 03_translate_md.py tests/unit/test_translate_step3_refactor.py
git commit -m "feat: add orchestrated phase cli contract"
```

### Task 2: Build Baoyu-Aligned Context Loader (Glossary/Preferences)

**Files:**
- Create: `ai/orchestration_context.py`
- Test: `tests/unit/test_orchestration_context.py`

**Step 1: Write the failing test**

```python
def test_load_context_merges_glossaries_in_deterministic_order(tmp_path):
    context = load_orchestration_context(...)
    assert "Stoicism" in context.glossary
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_orchestration_context.py::test_load_context_merges_glossaries_in_deterministic_order`
Expected: FAIL (module/function missing).

**Step 3: Write minimal implementation**

```python
@dataclass(slots=True)
class OrchestrationContext:
    audience: str
    style: str
    glossary: dict[str, str]
```

Implement loader from runtime config + built-in EN→ZH glossary path.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_orchestration_context.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add ai/orchestration_context.py tests/unit/test_orchestration_context.py
git commit -m "feat: add orchestration context loader"
```

### Task 3: Generate `01-analysis.md` with Baoyu Sections

**Files:**
- Create: `ai/orchestration_analysis.py`
- Modify: `ai/artifacts.py`
- Test: `tests/unit/test_orchestration_analysis.py`

**Step 1: Write the failing test**

```python
def test_analysis_contains_required_baoyu_sections(tmp_path):
    text = build_analysis_markdown(...)
    assert "## Quick Summary" in text
    assert "## Comprehension Challenges" in text
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_orchestration_analysis.py::test_analysis_contains_required_baoyu_sections`
Expected: FAIL.

**Step 3: Write minimal implementation**

Create deterministic section builder first; keep model-call hook injectable for future Pro/Flash switch.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_orchestration_analysis.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add ai/orchestration_analysis.py ai/artifacts.py tests/unit/test_orchestration_analysis.py
git commit -m "feat: add baoyu-style analysis artifact generation"
```

### Task 4: Assemble Rich `02-prompt.md` from Analysis + Context

**Files:**
- Create: `ai/orchestration_prompt.py`
- Test: `tests/unit/test_orchestration_prompt.py`

**Step 1: Write the failing test**

```python
def test_prompt_includes_audience_style_background_glossary_and_challenges():
    prompt = build_orchestration_prompt(...)
    assert "## Target Audience" in prompt
    assert "## Content Background" in prompt
    assert "## Glossary" in prompt
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_orchestration_prompt.py::test_prompt_includes_audience_style_background_glossary_and_challenges`
Expected: FAIL.

**Step 3: Write minimal implementation**

Implement prompt composer mirroring baoyu reference structure (shared context, no task-specific chunk instruction).

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_orchestration_prompt.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add ai/orchestration_prompt.py tests/unit/test_orchestration_prompt.py
git commit -m "feat: compose rich orchestration prompt from analysis context"
```

### Task 5: Refactor Orchestrator for Prompt-Only and Translate Phases

**Files:**
- Modify: `ai/orchestrator.py`
- Modify: `03_translate_md.py`
- Test: `tests/unit/test_orchestrator.py`
- Test: `tests/unit/test_translate_step3_refactor.py`

**Step 1: Write the failing test**

```python
def test_orchestrator_prompt_only_generates_analysis_and_prompt_without_outputs(tmp_path):
    result = run_orchestrated_translation(..., phase="prompt-only")
    assert result == {}
```

Also add:

```python
def test_orchestrator_translate_phase_uses_generated_prompt_for_each_page(...):
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_orchestrator.py tests/unit/test_translate_step3_refactor.py`
Expected: FAIL.

**Step 3: Write minimal implementation**

Add `phase` param to orchestrator; in `prompt-only`, write artifacts then return empty dict; in `translate`, perform per-page retries and collect failed pages for summary.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_orchestrator.py tests/unit/test_translate_step3_refactor.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add ai/orchestrator.py 03_translate_md.py tests/unit/test_orchestrator.py tests/unit/test_translate_step3_refactor.py
git commit -m "feat: add prompt-only orchestration phase and aligned translation flow"
```

### Task 6: Integration Coverage for Phase Behavior

**Files:**
- Modify: `tests/integration/test_step3_workflow_modes.py`
- Create: `tests/integration/test_step3_orchestrated_prompt_only.py`

**Step 1: Write the failing test**

```python
def test_orchestrated_prompt_only_writes_artifacts_without_output_pages(tmp_path):
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/integration/test_step3_orchestrated_prompt_only.py`
Expected: FAIL.

**Step 3: Write minimal implementation**

Adjust integration fixtures/stubs for new orchestrated phase contract.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/integration/test_step3_workflow_modes.py tests/integration/test_step3_orchestrated_prompt_only.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/integration/test_step3_workflow_modes.py tests/integration/test_step3_orchestrated_prompt_only.py
git commit -m "test: cover orchestrated prompt-only behavior"
```

### Task 7: Final Verification and Minimal Docs Sync

**Files:**
- Modify: `README.md` (or relevant section that documents Step3 flags)

**Step 1: Write/update docs tests (if any)**

If no docs test exists, skip this step and keep docs change minimal and factual.

**Step 2: Run quality gates**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
bash -n translatebook.sh
```

Expected: all pass.

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document orchestrated prompt-only phase and workflow alignment"
```

