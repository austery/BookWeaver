# SPEC-012 Final Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete SPEC-012 end-to-end by closing core config/glossary gaps, migrating legacy-script tests to hexagonal surfaces, strangling `03_translate_md.py` + `09_epub_translate_roundtrip.py`, rewiring `translatebook.sh` to `python -m ai.cli`, and enforcing `tach check` in CI.

**Architecture:** Keep `ai.core` as domain truth (`ConfigRegistry`, `GlossaryManager`), keep adapters/CLI as orchestration boundaries, and preserve behavior via TDD migration before deleting legacy entry scripts. Use strangler sequence: add new tests first, implement minimum code to pass, then safely delete and rewire.

**Tech Stack:** Python 3.13, pytest, ruff, tach, bash (`translatebook.sh`), GitHub Actions.

---

## File Structure & Responsibility Lock-in

### New files
- `ai/core/config.py`  
  Unified runtime configuration object for composition root and workflows.
- `ai/core/glossary.py`  
  Core glossary domain logic (load/filter/format + extraction orchestration facade).
- `tests/unit/test_core_config.py`  
  Unit tests for ConfigRegistry merge precedence and typed access.
- `tests/unit/test_core_glossary.py`  
  Unit tests for glossary load/filter/format/extract orchestration.
- `tests/integration/test_architecture.py` *(optional but recommended)*  
  Lightweight integration wrapper proving `tach check` command succeeds.

### Modified files
- `ai/cli.py`  
  Use `ConfigRegistry` + `GlossaryManager`; keep existing external flags stable.
- `ai/glossary_injector.py`  
  Compatibility shim delegating to `ai.core.glossary`.
- `ai/glossary_extractor.py`  
  Compatibility shim delegating to `ai.core.glossary`.
- `translatebook.sh`  
  Replace `03_translate_md.py` and `09_epub_translate_roundtrip.py` invocations with `python3 -m ai.cli`.
- `.github/workflows/lint.yml`  
  Add `uv run tach check` in CI quality gate.
- `tests/unit/test_translate_step3_refactor.py`  
  Migrate from `03_translate_md.py` coupling to `ai.cli`/core config surfaces.
- `tests/unit/test_epub_baseline_cli.py`  
  Remove `09_epub_translate_roundtrip.py` existence assumptions; validate `ai.cli`-based workflow contract.
- `tests/unit/test_glossary_in_epub_roundtrip.py`  
  Migrate prompt/glossary assertions to `ai.cli` + `ai.core.glossary`.
- `tests/unit/test_quality_gates.py`  
  Require `tach check` in workflow definition.
- `docs/architecture/specs/SPEC-012-core-translation-engine-hexagonal.md`  
  Mark remaining checklist items complete after verification.
- `README.md`  
  Remove obsolete references to deleted scripts from quickstart/pipeline sections.

### Deleted files
- `03_translate_md.py`
- `09_epub_translate_roundtrip.py`

---

### Task 1: Add `ai/core/config.py` (Unified ConfigRegistry)

**Files:**
- Create: `ai/core/config.py`
- Modify: `ai/cli.py`
- Test: `tests/unit/test_core_config.py`, `tests/unit/test_cli.py`

- [ ] **Step 1: Write failing ConfigRegistry tests**

```python
# tests/unit/test_core_config.py
from __future__ import annotations

import json
from pathlib import Path

from ai.core.config import ConfigRegistry


def test_registry_merges_paths_with_last_writer_wins(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    user = tmp_path / "user.json"
    base.write_text(json.dumps({"default_model": "gemini-2.5-flash", "model_probe": {"enabled": True}}))
    user.write_text(json.dumps({"default_model": "gemini-2.5-pro"}))

    cfg = ConfigRegistry.from_json_files([base, user])
    assert cfg.get_str("default_model") == "gemini-2.5-pro"
    assert cfg.get_bool("model_probe.enabled", default=False) is True


def test_registry_returns_defaults_for_missing_keys() -> None:
    cfg = ConfigRegistry({})
    assert cfg.get_str("not.exists", default="fallback") == "fallback"
    assert cfg.get_int("not.int", default=42) == 42
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/unit/test_core_config.py -q --tb=short`  
Expected: FAIL with `ModuleNotFoundError: No module named 'ai.core.config'`.

- [ ] **Step 3: Implement minimal ConfigRegistry**

```python
# ai/core/config.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass(frozen=True)
class ConfigRegistry:
    data: dict[str, Any]

    @classmethod
    def from_json_files(cls, paths: list[Path]) -> "ConfigRegistry":
        merged: dict[str, Any] = {}
        for path in paths:
            if not path.exists():
                continue
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError(f"Config must be JSON object: {path}")
            merged = _deep_merge(merged, loaded)
        return cls(merged)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        cursor: Any = self.data
        for part in dotted_key.split("."):
            if not isinstance(cursor, dict) or part not in cursor:
                return default
            cursor = cursor[part]
        return cursor

    def get_str(self, dotted_key: str, default: str | None = None) -> str | None:
        value = self.get(dotted_key, default)
        return value if isinstance(value, str) else default

    def get_bool(self, dotted_key: str, default: bool = False) -> bool:
        value = self.get(dotted_key, default)
        return value if isinstance(value, bool) else default

    def get_int(self, dotted_key: str, default: int = 0) -> int:
        value = self.get(dotted_key, default)
        return value if isinstance(value, int) else default
```

- [ ] **Step 4: Wire CLI to ConfigRegistry**

```python
# ai/cli.py (load_config)
from ai.core.config import ConfigRegistry

def load_config() -> dict[str, object]:
    script_dir = Path(__file__).resolve().parents[1]
    cfg = ConfigRegistry.from_json_files(
        [
            script_dir / "config" / "config.json.example",
            script_dir / "config" / "config.json",
            Path.home() / ".config" / "translatebook" / "config.json",
        ]
    )
    return cfg.data
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest tests/unit/test_core_config.py tests/unit/test_cli.py -q --tb=short`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai/core/config.py ai/cli.py tests/unit/test_core_config.py tests/unit/test_cli.py
git commit -m "feat(core): add unified ConfigRegistry and wire cli config loading"
```

---

### Task 2: Move glossary domain logic into `ai/core/glossary.py`

**Files:**
- Create: `ai/core/glossary.py`
- Modify: `ai/cli.py`, `ai/glossary_injector.py`, `ai/glossary_extractor.py`
- Test: `tests/unit/test_core_glossary.py`, `tests/unit/test_glossary_injector.py`, `tests/unit/test_glossary_extractor.py`, `tests/unit/test_cli.py`

- [ ] **Step 1: Write failing core glossary tests**

```python
# tests/unit/test_core_glossary.py
from __future__ import annotations

import json
from pathlib import Path

from ai.core.glossary import GlossaryManager


def test_format_block_filters_min_priority(tmp_path: Path) -> None:
    p = tmp_path / "g.json"
    p.write_text(
        json.dumps(
            {
                "critical_terminology": [
                    {"term": "A", "suggested_translation": "甲", "priority": "critical"},
                    {"term": "B", "suggested_translation": "乙", "priority": "medium"},
                ]
            }
        ),
        encoding="utf-8",
    )
    manager = GlossaryManager.from_json_file(p)
    block = manager.format_block(min_priority="high")
    assert "A" in block
    assert "B" not in block


def test_validate_model_output_requires_key() -> None:
    try:
        GlossaryManager.validate_model_output('{"wrong":[]}')
    except ValueError as exc:
        assert "critical_terminology" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/unit/test_core_glossary.py -q --tb=short`  
Expected: FAIL with `ModuleNotFoundError` for `ai.core.glossary`.

- [ ] **Step 3: Implement GlossaryManager**

```python
# ai/core/glossary.py
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ai.glossary_extractor import extract_epub_index_and_toc, _build_extraction_prompt


@dataclass(frozen=True)
class GlossaryManager:
    terms: list[dict]
    _order = {"critical": 0, "high": 1, "medium": 2}

    @classmethod
    def from_json_file(cls, path: Path) -> "GlossaryManager":
        data = json.loads(path.read_text(encoding="utf-8"))
        raw_terms = data.get("critical_terminology")
        if not isinstance(raw_terms, list):
            raise ValueError("Glossary missing 'critical_terminology'")
        terms = sorted(raw_terms, key=lambda t: cls._order.get(t.get("priority", "medium"), 2))
        return cls(terms=terms)

    def format_block(self, min_priority: str | None = None) -> str:
        terms = self.terms
        if min_priority is not None:
            cutoff = self._order.get(min_priority, 2)
            terms = [t for t in terms if self._order.get(t.get("priority", "medium"), 2) <= cutoff]
        if not terms:
            return ""
        lines = ["【关键术语约束】以下术语必须严格遵守标准译法："]
        for t in terms:
            line = f"  • {t.get('term', '')} → {t.get('suggested_translation', '')}"
            negative = t.get("negative_constraint", "")
            if negative:
                line += f"（{negative}）"
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def validate_model_output(raw_output: str) -> dict:
        cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw_output.strip())
        data = json.loads(cleaned)
        if "critical_terminology" not in data:
            raise ValueError("Model output missing 'critical_terminology'")
        return data

    @classmethod
    def extract_from_epub(
        cls,
        *,
        epub_path: Path,
        output_path: Path,
        translate_fn: Callable[[str], str],
        max_terms: int = 20,
        full_index: bool = False,
    ) -> dict:
        index_text, toc_text = extract_epub_index_and_toc(epub_path)
        prompt = _build_extraction_prompt(index_text, toc_text, max_terms, full_index=full_index)
        raw = translate_fn(prompt)
        parsed = cls.validate_model_output(raw)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        return parsed
```

- [ ] **Step 4: Rewire legacy glossary modules as compatibility shims**

```python
# ai/glossary_injector.py
from ai.core.glossary import GlossaryManager

class GlossaryInjector:
    def __init__(self, glossary_path: Path) -> None:
        self._manager = GlossaryManager.from_json_file(glossary_path)
    def format_block(self, min_priority: str | None = None) -> str:
        return self._manager.format_block(min_priority=min_priority)
```

```python
# ai/glossary_extractor.py (extract_glossary_from_epub)
from ai.core.glossary import GlossaryManager

def extract_glossary_from_epub(...):
    return GlossaryManager.extract_from_epub(
        epub_path=epub_path,
        output_path=output_path,
        translate_fn=translate_fn,
        max_terms=max_terms,
        full_index=full_index,
    )
```

- [ ] **Step 5: Run tests to verify pass**

Run:  
`uv run pytest tests/unit/test_core_glossary.py tests/unit/test_glossary_injector.py tests/unit/test_glossary_extractor.py tests/unit/test_cli.py -q --tb=short`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai/core/glossary.py ai/glossary_injector.py ai/glossary_extractor.py ai/cli.py tests/unit/test_core_glossary.py tests/unit/test_glossary_injector.py tests/unit/test_glossary_extractor.py tests/unit/test_cli.py
git commit -m "refactor(core): centralize glossary logic in core module"
```

---

### Task 3: Migrate legacy-script-coupled tests to hexagonal surfaces (TDD first)

**Files:**
- Modify: `tests/unit/test_translate_step3_refactor.py`
- Modify: `tests/unit/test_epub_baseline_cli.py`
- Modify: `tests/unit/test_glossary_in_epub_roundtrip.py`
- (Optional add): `tests/unit/test_cli_epub_workflow_contract.py`

- [ ] **Step 1: Replace Step3 script-coupled tests with ai.cli/core assertions**

```python
# tests/unit/test_translate_step3_refactor.py (new intent)
from ai.core.config import ConfigRegistry
from ai.cli import build_parser, build_system_prompt

def test_cli_accepts_model_override_flag() -> None:
    args = build_parser().parse_args(["book.epub", "--output", "out.epub", "--model", "gemini-2.5-pro"])
    assert args.model == "gemini-2.5-pro"

def test_prompt_builder_adds_custom_instruction_block() -> None:
    prompt = build_system_prompt("Chinese", custom_prompt="Keep technical terms unchanged.")
    assert "ADDITIONAL INSTRUCTIONS" in prompt
```

- [ ] **Step 2: Remove direct `09_epub_translate_roundtrip.py` existence assumptions**

```python
# tests/unit/test_epub_baseline_cli.py
def test_translatebook_uses_ai_cli_for_epub_workflow() -> None:
    content = Path("translatebook.sh").read_text(encoding="utf-8")
    assert "python3 -u -m ai.cli" in content
    assert "09_epub_translate_roundtrip.py" not in content
```

- [ ] **Step 3: Move glossary prompt-pollution assertions to ai.cli/core**

```python
# tests/unit/test_glossary_in_epub_roundtrip.py
from ai.cli import build_system_prompt

def test_glossary_block_is_in_system_prompt_not_input_content() -> None:
    prompt = build_system_prompt("Chinese", glossary_block="【关键术语约束】\n  • API → 接口")
    assert "关键术语约束" in prompt
```

- [ ] **Step 4: Run targeted suite**

Run:  
`uv run pytest tests/unit/test_translate_step3_refactor.py tests/unit/test_epub_baseline_cli.py tests/unit/test_glossary_in_epub_roundtrip.py -q --tb=short`  
Expected: PASS with no imports from deleted scripts.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_translate_step3_refactor.py tests/unit/test_epub_baseline_cli.py tests/unit/test_glossary_in_epub_roundtrip.py
git commit -m "test: migrate legacy script tests to hexagonal cli/core surfaces"
```

---

### Task 4: Strangle legacy entry scripts and rewire `translatebook.sh`

**Files:**
- Delete: `03_translate_md.py`, `09_epub_translate_roundtrip.py`
- Modify: `translatebook.sh`
- Modify: `README.md`
- Test: `tests/unit/test_translatebook_workflow_mode.py`, `tests/unit/test_translatebook_flag_compat.py`, `tests/unit/test_epub_baseline_cli.py`

- [ ] **Step 1: Add failing shell workflow tests for ai.cli invocations**

```python
# tests/unit/test_translatebook_flag_compat.py (new assertion)
def test_dry_run_epub_workflow_prints_ai_cli_command() -> None:
    ...
    assert "python3 -u -m ai.cli" in completed.stdout
```

- [ ] **Step 2: Run tests and capture failures**

Run:  
`uv run pytest tests/unit/test_translatebook_workflow_mode.py tests/unit/test_translatebook_flag_compat.py tests/unit/test_epub_baseline_cli.py -q --tb=short`  
Expected: FAIL until `translatebook.sh` is rewritten.

- [ ] **Step 3: Rewire EPUB workflow path to ai.cli**

```bash
# translatebook.sh (epub workflow command array)
cmd=(
  python3 -u -m ai.cli "$INPUT_FILE"
  --output "$translate_output"
  --input-format epub
  --output-lang "$OUTPUT_LANG"
  --provider "$PROVIDER"
)
[[ -n "$MODEL_OVERRIDE" ]] && cmd+=(--model "$MODEL_OVERRIDE")
[[ -n "$CUSTOM_PROMPT" ]] && cmd+=(-p "$CUSTOM_PROMPT")
[[ "$EXTRACT_GLOSSARY" == true ]] && cmd+=(--extract-glossary)
[[ -n "$GLOSSARY_PATH" ]] && cmd+=(--glossary "$GLOSSARY_PATH")
[[ -n "$GLOSSARY_MIN_PRIORITY" ]] && cmd+=(--glossary-min-priority "$GLOSSARY_MIN_PRIORITY")
[[ "$FALLBACK_PROVIDER" == "api" ]] && cmd+=(--cli-api-fallback)
```

- [ ] **Step 4: Rewire markdown workflow translation stage to ai.cli**

```bash
# translatebook.sh (step 3 replacement)
cmd=(
  python3 -u -m ai.cli "$base_temp_dir"
  --input-format markdown
  --output "${base_temp_dir}/output.md"
  --output-lang "$OUTPUT_LANG"
  --provider "$PROVIDER"
)
[[ -n "$MODEL_OVERRIDE" ]] && cmd+=(--model "$MODEL_OVERRIDE")
[[ -n "$CUSTOM_PROMPT" ]] && cmd+=(-p "$CUSTOM_PROMPT")
[[ -n "$GLOSSARY_PATH" ]] && cmd+=(--glossary "$GLOSSARY_PATH")
[[ -n "$GLOSSARY_MIN_PRIORITY" ]] && cmd+=(--glossary-min-priority "$GLOSSARY_MIN_PRIORITY")
[[ "$FALLBACK_PROVIDER" == "api" ]] && cmd+=(--cli-api-fallback)
```

- [ ] **Step 5: Delete legacy entry scripts**

```bash
git rm 03_translate_md.py 09_epub_translate_roundtrip.py
```

- [ ] **Step 6: Update docs references**

```markdown
# README.md pipeline section
1. `python -m ai.cli` (EPUB/PDF/Markdown routing + translation)
2. `05_md_to_html.py`
3. `06_add_toc.py`
4. `07_generate_formats.py`
```

- [ ] **Step 7: Run shell-focused tests**

Run:  
`uv run pytest tests/unit/test_translatebook_workflow_mode.py tests/unit/test_translatebook_flag_compat.py tests/unit/test_epub_baseline_cli.py tests/unit/test_translatebook_temp_dir.py -q --tb=short`  
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add translatebook.sh README.md tests/unit/test_translatebook_workflow_mode.py tests/unit/test_translatebook_flag_compat.py tests/unit/test_epub_baseline_cli.py tests/unit/test_translatebook_temp_dir.py
git commit -m "refactor(workflow): replace legacy step scripts with ai.cli entrypoint"
```

---

### Task 5: Enforce architecture boundaries in CI

**Files:**
- Modify: `.github/workflows/lint.yml`
- Modify: `tests/unit/test_quality_gates.py`
- (Optional Create): `tests/integration/test_architecture.py`

- [ ] **Step 1: Write failing quality-gate assertion for tach**

```python
# tests/unit/test_quality_gates.py
assert any(
    _command_contains_tokens(command, ("uv", "run", "tach", "check"))
    for command in lint_job.run_commands
), "Expected lint workflow to run 'uv run tach check'"
```

- [ ] **Step 2: Run quality-gate test to verify failure**

Run: `uv run pytest tests/unit/test_quality_gates.py -q --tb=short`  
Expected: FAIL because workflow lacks tach step.

- [ ] **Step 3: Add tach step to workflow**

```yaml
# .github/workflows/lint.yml
      - name: Tach architecture check
        run: uv run tach check
```

- [ ] **Step 4: (Optional) Add integration wrapper**

```python
# tests/integration/test_architecture.py
from __future__ import annotations

import subprocess

def test_tach_check_passes() -> None:
    completed = subprocess.run(["uv", "run", "tach", "check"], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
```

- [ ] **Step 5: Run tests and commit**

Run:  
`uv run pytest tests/unit/test_quality_gates.py tests/integration/test_architecture.py -q --tb=short`  
Expected: PASS.

```bash
git add .github/workflows/lint.yml tests/unit/test_quality_gates.py tests/integration/test_architecture.py
git commit -m "ci: enforce tach architecture checks in lint gate"
```

---

### Task 6: Final verification + SPEC-012 completion mark

**Files:**
- Modify: `docs/architecture/specs/SPEC-012-core-translation-engine-hexagonal.md`
- Modify: `/Users/leipeng/.copilot/session-state/29f05d2e-ed1f-4441-b38b-8bc99af6cfa3/plan.md`

- [ ] **Step 1: Run full verification suite**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run tach check
uv run pytest -q -x --tb=short -p no:tach
bash -n translatebook.sh
```

Expected: all checks pass.

- [ ] **Step 2: Perform smoke dry-runs**

Run:

```bash
./translatebook.sh --dry-run --workflow epub /tmp/demo.epub
./translatebook.sh --dry-run --workflow markdown /tmp/demo.pdf
```

Expected: command output shows `python3 -u -m ai.cli` path and no references to removed scripts.

- [ ] **Step 3: Mark SPEC-012 completed**

```markdown
# docs/architecture/specs/SPEC-012-core-translation-engine-hexagonal.md
status: ✅ 已完成 (Completed)
lastUpdateDate: 2026-03-29
```

Set all remaining checklist entries that are now delivered to `[x]`, and add short note of CI enforcement (`tach check` in workflow).

- [ ] **Step 4: Final commit**

```bash
git add docs/architecture/specs/SPEC-012-core-translation-engine-hexagonal.md /Users/leipeng/.copilot/session-state/29f05d2e-ed1f-4441-b38b-8bc99af6cfa3/plan.md
git commit -m "docs(spec): mark SPEC-012 complete after core closeout and CI enforcement"
```

---

## Spec Coverage Self-Review

- Phase 1 gap (core config): covered by Task 1.
- Phase 2 gap (core glossary relocation): covered by Task 2.
- Test migration before deletion: covered by Task 3, executed before Task 4.
- Legacy strangler + shell rewire: covered by Task 4.
- Architecture enforcement in CI: covered by Task 5.
- Completion signal + verification: covered by Task 6.

No placeholder markers (`TODO/TBD`) are left in tasks. Task ordering enforces TDD + dependency chain.
