# SPEC-004 Orchestrated Evaluation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an opt-in `orchestrated` Step-3 workflow with artifact traceability and measurable quality/runtime gates, while keeping the existing `fast` flow fully backward-compatible.

**Architecture:** Keep `fast` as the default path, add mode dispatch at Step 3, and isolate orchestration concerns into small modules (`mode_contract`, `artifacts`, `orchestrator`, `evaluation`). Preserve the existing Step 3 output contract (`output_pageXXXX.md`) so Step 4-7 remain unchanged.

**Tech Stack:** Python 3.11, Bash, pytest, ruff, uv, Gemini CLI

---

### Task 1: Add workflow mode contract module

**Files:**
- Create: `ai/mode_contract.py`
- Test: `tests/unit/test_mode_contract.py`

**Step 1: Write the failing test**

```python
from ai.mode_contract import DEFAULT_WORKFLOW_MODE, parse_workflow_mode


def test_parse_workflow_mode_accepts_fast_and_orchestrated() -> None:
    assert parse_workflow_mode("fast") == "fast"
    assert parse_workflow_mode("orchestrated") == "orchestrated"
    assert DEFAULT_WORKFLOW_MODE == "fast"


def test_parse_workflow_mode_rejects_unknown_value() -> None:
    try:
        parse_workflow_mode("unknown")
    except ValueError as exc:
        assert "workflow mode" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError for invalid mode")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_mode_contract.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai.mode_contract'`

**Step 3: Write minimal implementation**

```python
from typing import Literal

WorkflowMode = Literal["fast", "orchestrated", "auto"]
DEFAULT_WORKFLOW_MODE: WorkflowMode = "fast"


def parse_workflow_mode(raw: str | None) -> WorkflowMode:
    normalized = (raw or DEFAULT_WORKFLOW_MODE).strip().lower()
    if normalized in {"fast", "orchestrated", "auto"}:
        return normalized
    raise ValueError(f"Invalid workflow mode: {raw}")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_mode_contract.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add ai/mode_contract.py tests/unit/test_mode_contract.py
git commit -m "feat: add workflow mode contract parser"
```

### Task 2: Wire workflow mode into Step 3 CLI parsing and dispatch

**Files:**
- Modify: `03_translate_md.py:464-590`
- Test: `tests/unit/test_translate_step3_refactor.py`

**Step 1: Write the failing test**

```python
def test_step3_parse_arguments_accepts_workflow_mode(monkeypatch):
    module = _load_step3_module()
    monkeypatch.setattr(
        sys,
        "argv",
        ["03_translate_md.py", "--temp-dir", "/tmp/demo", "--workflow-mode", "orchestrated"],
    )
    args = module.parse_arguments()
    assert args.workflow_mode == "orchestrated"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_translate_step3_refactor.py::test_step3_parse_arguments_accepts_workflow_mode -q`
Expected: FAIL with argparse unknown argument `--workflow-mode`

**Step 3: Write minimal implementation**

```python
parser.add_argument(
    "--workflow-mode",
    default="fast",
    help="Workflow mode: fast|orchestrated|auto (default: fast)",
)
```

```python
from ai.mode_contract import parse_workflow_mode

workflow_mode = parse_workflow_mode(args.workflow_mode)
print(f"Workflow mode: {workflow_mode}")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_translate_step3_refactor.py::test_step3_parse_arguments_accepts_workflow_mode -q`
Expected: PASS

**Step 5: Commit**

```bash
git add 03_translate_md.py tests/unit/test_translate_step3_refactor.py
git commit -m "feat: add workflow-mode argument to step3"
```

### Task 3: Propagate workflow mode from `translatebook.sh` to Step 3 command

**Files:**
- Modify: `translatebook.sh:14-32`
- Modify: `translatebook.sh:64-95`
- Modify: `translatebook.sh:269-391`
- Modify: `translatebook.sh:647-756`
- Test: `tests/unit/test_translatebook_workflow_mode.py`

**Step 1: Write the failing test**

```python
def test_help_includes_workflow_mode_flag() -> None:
    completed = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--workflow-mode MODE" in completed.stdout
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_translatebook_workflow_mode.py -q`
Expected: FAIL because help output does not contain `--workflow-mode`

**Step 3: Write minimal implementation**

```bash
WORKFLOW_MODE="fast"
```

```bash
--workflow-mode)
    WORKFLOW_MODE="$2"
    shift 2
    ;;
```

```bash
if [[ ! "$WORKFLOW_MODE" =~ ^(fast|orchestrated|auto)$ ]]; then
    log_error "Invalid workflow mode: $WORKFLOW_MODE (must be fast|orchestrated|auto)"
    exit 2
fi
```

```bash
cmd="$cmd --workflow-mode \"$WORKFLOW_MODE\""
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_translatebook_workflow_mode.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add translatebook.sh tests/unit/test_translatebook_workflow_mode.py
git commit -m "feat: pass workflow-mode from script to step3"
```

### Task 4: Add orchestration artifact persistence helpers

**Files:**
- Create: `ai/artifacts.py`
- Test: `tests/unit/test_artifacts.py`

**Step 1: Write the failing test**

```python
from pathlib import Path
from ai.artifacts import OrchestrationArtifacts


def test_artifacts_paths_and_metrics_write(tmp_path: Path) -> None:
    artifacts = OrchestrationArtifacts(tmp_path)
    analysis_path = artifacts.analysis_path()
    artifacts.write_text(analysis_path, "analysis content")
    artifacts.write_metrics({"runtime_ratio": 1.8})
    assert analysis_path.exists()
    assert artifacts.metrics_path().exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_artifacts.py -q`
Expected: FAIL with missing module/class

**Step 3: Write minimal implementation**

```python
@dataclass
class OrchestrationArtifacts:
    temp_dir: Path

    def root(self) -> Path: ...
    def analysis_path(self) -> Path: ...
    def prompt_path(self) -> Path: ...
    def metrics_path(self) -> Path: ...
    def write_text(self, path: Path, content: str) -> None: ...
    def write_metrics(self, metrics: dict[str, float | int | str]) -> None: ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_artifacts.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add ai/artifacts.py tests/unit/test_artifacts.py
git commit -m "feat: add orchestration artifact helpers"
```

### Task 5: Add orchestrated runner and keep output contract compatibility

**Files:**
- Create: `ai/orchestrator.py`
- Modify: `03_translate_md.py:506-587`
- Test: `tests/unit/test_orchestrator.py`
- Test: `tests/integration/test_step3_workflow_modes.py`

**Step 1: Write the failing test**

```python
def test_orchestrated_mode_writes_analysis_and_prompt_artifacts(tmp_path: Path) -> None:
    orchestrator = TranslationOrchestrator(temp_dir=tmp_path)
    orchestrator.run_analysis("source chunk")
    orchestrator.run_prompt_assembly("zh", "custom")
    assert (tmp_path / "orchestration" / "01-analysis.md").exists()
    assert (tmp_path / "orchestration" / "02-prompt.md").exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_orchestrator.py -q`
Expected: FAIL with missing orchestrator implementation

**Step 3: Write minimal implementation**

```python
class TranslationOrchestrator:
    def run(self, workflow_mode: WorkflowMode, ... ) -> None:
        if workflow_mode == "fast":
            return self._run_fast(...)
        return self._run_orchestrated(...)
```

```python
# 03_translate_md.py
if workflow_mode == "fast":
    translate_markdown_files(...)
else:
    orchestrator = TranslationOrchestrator(...)
    orchestrator.run(...)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_orchestrator.py tests/integration/test_step3_workflow_modes.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add ai/orchestrator.py 03_translate_md.py tests/unit/test_orchestrator.py tests/integration/test_step3_workflow_modes.py
git commit -m "feat: add orchestrated step3 execution path"
```

### Task 6: Implement weighted evaluation and gate checks

**Files:**
- Create: `ai/evaluation.py`
- Modify: `benchmark_models.py`
- Test: `tests/unit/test_evaluation.py`
- Test: `tests/unit/test_benchmark_models.py`

**Step 1: Write the failing test**

```python
from ai.evaluation import weighted_quality_score, gate1_passed


def test_weighted_quality_score_uses_spec004_weights() -> None:
    score = weighted_quality_score(terminology=80, fidelity=70, fluency=60)
    assert round(score, 2) == 71.50


def test_gate1_passed_requires_quality_and_runtime_constraints() -> None:
    assert gate1_passed(quality_delta=5.1, runtime_ratio=1.9) is True
    assert gate1_passed(quality_delta=4.9, runtime_ratio=1.9) is False
    assert gate1_passed(quality_delta=5.1, runtime_ratio=2.1) is False
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_evaluation.py -q`
Expected: FAIL with missing module/functions

**Step 3: Write minimal implementation**

```python
def weighted_quality_score(terminology: float, fidelity: float, fluency: float) -> float:
    return 0.40 * terminology + 0.35 * fidelity + 0.25 * fluency


def gate1_passed(quality_delta: float, runtime_ratio: float) -> bool:
    return quality_delta >= 5.0 and runtime_ratio <= 2.0
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_evaluation.py tests/unit/test_benchmark_models.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add ai/evaluation.py benchmark_models.py tests/unit/test_evaluation.py tests/unit/test_benchmark_models.py
git commit -m "feat: add spec004 weighted evaluation and gate checks"
```

### Task 7: Regression and documentation alignment

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `docs/architecture/specs/SPEC-004-baoyu-agent-orchestrated-translation-evaluation.md` (if implementation details diverged)
- Test: `tests/unit/test_translate_step3_refactor.py`
- Test: `tests/unit/test_quality_gates.py`

**Step 1: Write the failing test**

```python
def test_step3_preview_includes_workflow_mode(monkeypatch):
    ...
    assert "Workflow mode:" in captured_output
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_translate_step3_refactor.py::test_step3_preview_includes_workflow_mode -q`
Expected: FAIL before docs/UX alignment patch

**Step 3: Write minimal implementation**

```python
print(f"Workflow mode: {workflow_mode}")
```

Update docs to reflect:

- `--workflow-mode fast|orchestrated|auto`
- Gate 1 threshold (`+5`, `<=2.0x`)
- Gate 2 refined-loop condition

**Step 4: Run full verification**

Run:

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest -q`
- `bash -n translatebook.sh`
- `uv run python -m py_compile 03_translate_md.py ai/gemini_provider.py ai/model_probe.py 05_md_to_html.py 07_generate_formats.py`

Expected: all commands pass

**Step 5: Commit**

```bash
git add README.md CLAUDE.md docs/architecture/specs/SPEC-004-baoyu-agent-orchestrated-translation-evaluation.md 03_translate_md.py tests/unit/test_translate_step3_refactor.py
git commit -m "docs: align workflow-mode and evaluation gates"
```
