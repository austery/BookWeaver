# Dynamic Prompt + Refined Minimal Evaluation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a minimal, gated `orchestrated` Step-3 evaluation path (analysis + dynamic `02-prompt` + critique/revision/polish) and compare it against `fast` using fixed quality/runtime gates, without changing downstream Step 4-7 contracts.

**Architecture:** Build thin orchestration modules in `ai/` (`artifacts`, `orchestrator`, `evaluation`), wire explicit mode dispatch in `03_translate_md.py`, and keep output compatibility by always emitting `output_pageXXXX.md`. Persist all orchestration artifacts under `<temp_dir>/orchestration/` and record benchmark metrics for go/no-go decisions.

**Tech Stack:** Python 3.14, pytest, uv, existing BookWeaver step pipeline, Gemini CLI provider integration

---

### Task 1: Add orchestration artifact persistence module

**Files:**
- Create: `ai/artifacts.py`
- Test: `tests/unit/test_artifacts.py`

**Step 1: Write the failing test**

```python
from pathlib import Path
import json

from ai.artifacts import OrchestrationArtifacts


def test_artifacts_write_paths_and_metrics(tmp_path: Path) -> None:
    artifacts = OrchestrationArtifacts(temp_dir=tmp_path)
    analysis = artifacts.analysis_path()
    prompt = artifacts.prompt_path()
    metrics = artifacts.metrics_path()

    artifacts.write_text(analysis, "analysis")
    artifacts.write_text(prompt, "prompt")
    artifacts.write_metrics({"runtime_ratio": 1.8, "quality_delta": 5.2})

    assert analysis.exists()
    assert prompt.exists()
    assert metrics.exists()
    payload = json.loads(metrics.read_text(encoding="utf-8"))
    assert payload["runtime_ratio"] == 1.8
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_artifacts.py`

Expected: FAIL with `ModuleNotFoundError` for `ai.artifacts`.

**Step 3: Write minimal implementation**

```python
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class OrchestrationArtifacts:
    temp_dir: Path

    def root(self) -> Path:
        return self.temp_dir / "orchestration"

    def analysis_path(self) -> Path:
        return self.root() / "01-analysis.md"

    def prompt_path(self) -> Path:
        return self.root() / "02-prompt.md"

    def translation_dir(self) -> Path:
        return self.root() / "03-translation"

    def critique_path(self) -> Path:
        return self.root() / "04-critique.md"

    def revision_path(self) -> Path:
        return self.root() / "05-revision.md"

    def polish_path(self) -> Path:
        return self.root() / "06-polish.md"

    def metrics_path(self) -> Path:
        return self.root() / "metrics.json"

    def write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def write_metrics(self, payload: dict[str, Any]) -> None:
        metrics = self.metrics_path()
        metrics.parent.mkdir(parents=True, exist_ok=True)
        metrics.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_artifacts.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add ai/artifacts.py tests/unit/test_artifacts.py
git commit -m "feat: add orchestration artifact persistence helpers"
```

---

### Task 2: Add weighted evaluation scoring module

**Files:**
- Create: `ai/evaluation.py`
- Test: `tests/unit/test_evaluation.py`

**Step 1: Write the failing test**

```python
from ai.evaluation import weighted_quality_score, gate_decision


def test_weighted_quality_score_formula() -> None:
    score = weighted_quality_score(terminology=80, fidelity=70, fluency=60)
    assert round(score, 2) == 71.5


def test_gate_decision_requires_both_thresholds() -> None:
    result = gate_decision(quality_delta=5.0, runtime_ratio=2.0)
    assert result == "adopt"
    assert gate_decision(quality_delta=4.9, runtime_ratio=1.8) == "defer"
    assert gate_decision(quality_delta=5.2, runtime_ratio=2.1) == "defer"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_evaluation.py`

Expected: FAIL with missing module.

**Step 3: Write minimal implementation**

```python
from __future__ import annotations


def weighted_quality_score(*, terminology: float, fidelity: float, fluency: float) -> float:
    return 0.40 * terminology + 0.35 * fidelity + 0.25 * fluency


def gate_decision(*, quality_delta: float, runtime_ratio: float) -> str:
    if quality_delta >= 5.0 and runtime_ratio <= 2.0:
        return "adopt"
    return "defer"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_evaluation.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add ai/evaluation.py tests/unit/test_evaluation.py
git commit -m "feat: add weighted quality gate evaluation module"
```

---

### Task 3: Add orchestrator skeleton with artifact generation

**Files:**
- Create: `ai/orchestrator.py`
- Test: `tests/unit/test_orchestrator.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

from ai.orchestrator import run_orchestrated_translation


def test_orchestrator_writes_required_artifacts(tmp_path: Path) -> None:
    pages = {"page0001.md": "Source paragraph."}
    result = run_orchestrated_translation(
        temp_dir=tmp_path,
        pages=pages,
        output_lang="zh",
    )
    assert (tmp_path / "orchestration" / "01-analysis.md").exists()
    assert (tmp_path / "orchestration" / "02-prompt.md").exists()
    assert (tmp_path / "orchestration" / "04-critique.md").exists()
    assert (tmp_path / "orchestration" / "05-revision.md").exists()
    assert (tmp_path / "orchestration" / "06-polish.md").exists()
    assert "page0001.md" in result
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_orchestrator.py`

Expected: FAIL with missing module/function.

**Step 3: Write minimal implementation**

```python
from __future__ import annotations

from pathlib import Path

from ai.artifacts import OrchestrationArtifacts


def run_orchestrated_translation(
    *,
    temp_dir: Path,
    pages: dict[str, str],
    output_lang: str,
) -> dict[str, str]:
    artifacts = OrchestrationArtifacts(temp_dir=temp_dir)
    artifacts.write_text(artifacts.analysis_path(), f"analysis for {len(pages)} pages")
    artifacts.write_text(artifacts.prompt_path(), f"translate to {output_lang}")
    artifacts.write_text(artifacts.critique_path(), "critique")
    artifacts.write_text(artifacts.revision_path(), "revision")
    artifacts.write_text(artifacts.polish_path(), "polish")
    artifacts.write_metrics({"mode": "orchestrated", "pages": len(pages)})
    return {name: f"ORCH:{content}" for name, content in pages.items()}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_orchestrator.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add ai/orchestrator.py tests/unit/test_orchestrator.py
git commit -m "feat: add minimal orchestrated translation runner"
```

---

### Task 4: Wire `03_translate_md.py` mode dispatch to orchestrator

**Files:**
- Modify: `03_translate_md.py:19-25`
- Modify: `03_translate_md.py:376-460`
- Modify: `03_translate_md.py:512-600`
- Test: `tests/unit/test_translate_step3_refactor.py`

**Step 1: Write the failing test**

```python
def test_step3_orchestrated_mode_routes_to_orchestrator(tmp_path, monkeypatch):
    module = _load_step3_module()
    captured = {}

    def fake_orchestrated(*, temp_dir, pages, output_lang):
        captured["called"] = True
        return {name: f"ORCH:{text}" for name, text in pages.items()}

    monkeypatch.setattr(module, "run_orchestrated_translation", fake_orchestrated)
    monkeypatch.setattr(module, "glob", __import__("glob"))
    # Prepare minimal temp dir with one page file and config to invoke translation path...
    # Assert orchestrator was called when workflow_mode == "orchestrated"
```

(Use existing helper patterns already present in `tests/unit/test_translate_step3_refactor.py`.)

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_translate_step3_refactor.py::test_step3_orchestrated_mode_routes_to_orchestrator`

Expected: FAIL (orchestrator not yet wired).

**Step 3: Write minimal implementation**

1. Import orchestrator:

```python
from ai.orchestrator import run_orchestrated_translation
```

2. In translation path, branch by parsed `workflow_mode`:

```python
if workflow_mode == "orchestrated":
    # load source page files into dict
    orchestrated_outputs = run_orchestrated_translation(
        temp_dir=Path(temp_dir),
        pages=source_pages,
        output_lang=output_lang,
    )
    # write orchestrated outputs back to output_pageXXXX.md contract
else:
    # existing fast path unchanged
```

3. Preserve existing `fast` behavior and logs.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_translate_step3_refactor.py::test_step3_orchestrated_mode_routes_to_orchestrator`

Expected: PASS.

**Step 5: Commit**

```bash
git add 03_translate_md.py tests/unit/test_translate_step3_refactor.py
git commit -m "feat: wire step3 orchestrated mode dispatch"
```

---

### Task 5: Add Step-3 output compatibility integration test

**Files:**
- Create: `tests/integration/test_step3_workflow_modes.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_fast_and_orchestrated_emit_output_page_contract(tmp_path: Path) -> None:
    # prepare temp dir with page0001.md + config
    # run step3 in fast mode (with mocked translation function)
    # run step3 in orchestrated mode
    # assert both produce output_page0001.md and non-empty text
    # assert downstream naming contract is identical
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/integration/test_step3_workflow_modes.py`

Expected: FAIL before dispatch/contract handling is complete.

**Step 3: Write minimal implementation adjustments**

If needed, add tiny adapter helpers in `03_translate_md.py` to avoid duplicated write logic between modes.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/integration/test_step3_workflow_modes.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/integration/test_step3_workflow_modes.py 03_translate_md.py
git commit -m "test: enforce step3 output contract across workflow modes"
```

---

### Task 6: Add benchmark command and gate decision recording

**Files:**
- Modify: `benchmark_models.py`
- Test: `tests/unit/test_benchmark_models.py`
- Optional docs note: `README.md` (if CLI usage text changes)

**Step 1: Write the failing test**

```python
def test_benchmark_reports_quality_delta_runtime_ratio_and_gate(tmp_path):
    # run benchmark compare helper with synthetic scores/times
    # assert output payload includes:
    # - quality_delta
    # - runtime_ratio
    # - gate_decision
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_benchmark_models.py::test_benchmark_reports_quality_delta_runtime_ratio_and_gate`

Expected: FAIL due to missing fields.

**Step 3: Write minimal implementation**

Use `ai.evaluation.weighted_quality_score` + `gate_decision` and persist explicit decision string.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_benchmark_models.py::test_benchmark_reports_quality_delta_runtime_ratio_and_gate`

Expected: PASS.

**Step 5: Commit**

```bash
git add benchmark_models.py tests/unit/test_benchmark_models.py README.md
git commit -m "feat: record orchestrated evaluation gate decision in benchmark output"
```

---

### Task 7: Full verification and branch handoff

**Files:**
- No functional code files added in this task

**Step 1: Run focused new tests**

Run:

`uv run pytest -q tests/unit/test_artifacts.py tests/unit/test_evaluation.py tests/unit/test_orchestrator.py tests/unit/test_mode_contract.py tests/unit/test_translate_step3_refactor.py tests/integration/test_step3_workflow_modes.py`

Expected: PASS.

**Step 2: Run full quality gates**

Run:

`uv run ruff check . && uv run ruff format --check . && uv run pytest -q && bash -n translatebook.sh`

Expected: all green.

**Step 3: Sanity check CLI behavior**

Run:

`./translatebook.sh --dry-run --workflow-mode fast /path/to/book.epub`

`./translatebook.sh --dry-run --workflow-mode orchestrated /path/to/book.epub`

Expected:

- mode is shown correctly in Step 3 logs
- no silent fallback in explicit orchestrated mode

**Step 4: Summarize benchmark gate decision**

Produce concise report with:

- weighted quality delta
- runtime ratio
- gate decision (`adopt`/`defer`)
- rationale

**Step 5: Commit (if any final doc/report updates)**

```bash
git add <changed-files>
git commit -m "docs: finalize minimal orchestrated evaluation gate summary"
```

