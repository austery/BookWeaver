# Design: Comprehensive PR Review Cleanup (TDD)

**Date:** 2026-03-22
**Branch:** `fix/pr-review-comprehensive-cleanup`
**Scope:** All 18 critical/important issues + 12 suggestions from the 2026-03-22 codebase review
**Method:** TDD — every behavioral change is preceded by a failing test

---

## Goals

1. Fix all identified bugs, silent failures, and error handling gaps
2. Extract duplicated logic into shared utilities
3. Achieve full type annotation coverage on legacy pipeline scripts
4. Enforce ANN ruff rules to prevent future annotation drift
5. Improve test coverage with ~22 new tests
6. Correct stale documentation and wrong script name references
7. Zero functional regressions — every commit passes `ruff check` and `pytest -q`

## Non-Goals

- SPEC-007 unified YAML configuration (config overhaul is a separate initiative)
- New pipeline features
- Changes to EPUB workflow logic or translation behavior

---

## Architecture

### New File: `pipeline_utils.py` (root level)

Infrastructure-layer utilities shared by pipeline scripts. Intentionally placed at root (same layer as pipeline scripts) rather than inside `ai/` (domain layer) to respect Clean Architecture separation.

```
BookWeaver/
├── pipeline_utils.py          ← NEW: load_pipeline_config, get_language_name
├── 01_convert_to_htmlz.py     ← imports from pipeline_utils
├── 02_split_to_md.py          ← imports from pipeline_utils
├── 03_translate_md.py         ← imports from pipeline_utils + RuntimeConfig TypedDict
├── 06_add_toc.py              ← imports from pipeline_utils
├── 07_generate_formats.py     ← imports from pipeline_utils
├── ai/
│   └── epub_translate_roundtrip.py  ← imports get_language_name from pipeline_utils
└── tests/unit/
    └── test_pipeline_utils.py ← NEW
```

### RuntimeConfig TypedDict (03_translate_md.py)

Replace all `dict[str, Any]` usages with a typed `RuntimeConfig` TypedDict, eliminating the `Any` violation:

```python
class RuntimeConfig(TypedDict):
    model: str
    input_lang: str
    output_lang: str
    temp_dir: str
    prompt_profile: str
    prompt_templates: dict[str, str]
    model_aliases: dict[str, str]
    model_thresholds: dict[str, int | None]
```

---

## Implementation Plan: 7 Commits

### Commit 1 — Dead Code Removal
`chore: remove dead code and unused imports`

**Changes (no tests required — ruff validates):**

| File | Action |
|------|--------|
| `07_generate_formats.py:36-144` | Delete `translate_title_with_claude` function entirely |
| `07_generate_formats.py:42` | Remove redundant inner `import subprocess` |
| `01_prepare_env.py:14` | Remove unused `import shutil` |
| `02_split_to_md.py:13-14` | Remove unused `import io`, `import json` |
| `01_convert_to_htmlz.py:10` | Remove unused `from typing import Any` |

**Verification:** `uv run ruff check .` → 0 errors; `uv run pytest -q` → all green

---

### Commit 2 — Shared Utilities Extraction
`refactor: extract pipeline_utils.py with load_pipeline_config and get_language_name`

**TDD sequence:**

1. Write `tests/unit/test_pipeline_utils.py` (RED):
   - `test_load_pipeline_config_returns_dict` — valid config.txt parses to dict
   - `test_load_pipeline_config_file_not_found` — missing file raises `FileNotFoundError` with message "Run 01_convert_to_htmlz.py first"
   - `test_load_pipeline_config_unicode_error` — non-UTF-8 file raises `UnicodeDecodeError`
   - `test_get_language_name_known_codes` — `"zh"` → `"Chinese"`, `"en"` → `"English"`, etc.
   - `test_get_language_name_unknown_code` — unknown code returned as-is

2. Create `pipeline_utils.py` (GREEN):
   ```python
   from __future__ import annotations
   import os

   def load_pipeline_config(temp_dir: str) -> dict[str, str]:
       """Load pipeline config.txt written by 01_convert_to_htmlz.py.

       Raises:
           FileNotFoundError: if config.txt not found in temp_dir.
               Message includes actionable hint to run step 1 first.
           UnicodeDecodeError: if file contains non-UTF-8 bytes.
       """
       ...

   def get_language_name(code: str) -> str:
       """Convert ISO language code to full name. Returns code as-is if unknown."""
       ...
   ```
   Language mapping is the union of all three existing implementations (14+ languages).

3. Replace duplicate implementations in `03_translate_md.py`, `06_add_toc.py`, `07_generate_formats.py`, `01_convert_to_htmlz.py`, `02_split_to_md.py`, `ai/epub_translate_roundtrip.py`.

**Verification:** `uv run pytest -q` → new tests GREEN; no existing tests broken

---

### Commit 3 — Core Bug Fixes
`fix: harden _read_zip_text, json config loading, ebook-convert, and checkpoint warnings`

**TDD sequence — write these 4 tests first (RED):**

| Test file | Test name | Expected behavior |
|-----------|-----------|------------------|
| `test_epub_translate_roundtrip.py` | `test_read_zip_text_missing_entry_raises_value_error` | Missing ZIP entry → `ValueError("EPUB missing required file: <path>")` not bare `KeyError` |
| `test_translate_step3_refactor.py` | `test_load_runtime_config_invalid_json_raises_with_message` | Malformed user config JSON → `json.JSONDecodeError` with file path in message |
| `test_generate_formats_step7.py` | `test_run_ebook_convert_not_installed_returns_false` | `ebook-convert` absent → returns `False`, prints "ebook-convert not found. Install Calibre." |
| `test_epub_translate_roundtrip.py` | `test_checkpoint_mismatch_prints_warning` | Model change → stdout contains `[WARN] Checkpoint invalidated` |

**Then make GREEN:**
- `ai/epub_translate_roundtrip.py:436` — replace local `_read_zip_text` with hardened version from `epub_package.py` (adds `KeyError` → `ValueError` and `UnicodeDecodeError` → `ValueError` guards)
- `03_translate_md.py:82` — wrap each `json.load()` in `try/except json.JSONDecodeError` with message containing the file path
- `07_generate_formats.py:243` — add `except FileNotFoundError: log_error("ebook-convert not found. Install Calibre."); return False`
- `ai/epub_translate_roundtrip.py:196–234` — add `print(f"[WARN] Checkpoint invalidated: <field> changed ...")` to each metadata mismatch branch

---

### Commit 4 — Error Handling Improvements
`fix: narrow broad Exception catches in 01_convert_to_htmlz.py and 02_split_to_md.py`

**TDD sequence — write 3 tests first (RED):**

| Test file | Test name | Expected behavior |
|-----------|-----------|------------------|
| `test_generate_formats_step7.py` | `test_run_ebook_convert_called_process_error_returns_false` | `CalledProcessError` → returns `False`, logs stderr content |
| `test_translate_step3_refactor.py` | `test_load_runtime_config_permission_error` | Config file unreadable → `PermissionError` containing the file path |
| (existing `test_pipeline_utils.py`) | already covers `load_config` errors | — |

**Then make GREEN — `01_convert_to_htmlz.py` (7 broad except locations):**

| Line | Current | Fix |
|------|---------|-----|
| 62 | `except Exception` | keep broad but add specific `zipfile.BadZipFile` branch first with "corrupted" message |
| 127 | `except Exception` | add `except ET.ParseError` first with "OPF metadata malformed" message |
| 188 | `except Exception` | add `except zipfile.BadZipFile` first with path and "corrupted" message |
| 222 | `except Exception` | add `except OSError` with source/dest paths |
| 264 | `except Exception` | add `except OSError` with file path |
| 358 | `except Exception` | add `except MemoryError` and `except OSError` before broad catch |
| 398 | `except Exception` | add `except OSError` with config path |

**`02_split_to_md.py`:**
- `load_config:21` — wrap in `try/except FileNotFoundError`, message: "config.txt not found. Run 01_convert_to_htmlz.py first." (fixes Issue 18 simultaneously)
- `convert_to_pdf_calibre:77` — `raise Exception(...)` → `raise RuntimeError(...) from e`
- `split_pdf_to_md:600` — preserve `CalledProcessError.stderr` in error message before `sys.exit(1)`

---

### Commit 5 — Test Coverage + Quality Fixes
`test: fill coverage gaps and improve test quality`

**Pure test commit — no business logic changes:**

| Test file | Test(s) | Issue |
|-----------|---------|-------|
| `test_quota_tracker.py` | `test_record_usage_negative_raises` | Issue 14 |
| `test_quota_tracker.py` | `test_get_daily_usage_cross_date_isolation` | Issue 14 |
| `test_quota_tracker.py` | `test_get_daily_usage_no_records_returns_zero` | Issue 14 |
| `test_model_selector.py` | `test_select_at_exact_small_threshold` | Issue 15 |
| `test_model_selector.py` | `test_select_at_exact_medium_threshold` | Issue 15 |
| `test_translate_step3_refactor.py` | `test_translate_files_resume_skips_existing` | Issue 16 |
| `test_translate_step3_refactor.py` | `test_deep_merge_dict_nested_merge` | S8 |
| `test_translate_step3_refactor.py` | `test_resolve_model_alias_cycle_detection` | error-reviewer gap |
| `test_bilingual_merger.py` | Rewrite manual `try/except` → `pytest.raises` | S6 |
| `test_epub_translate_batching.py` | Remove exact batch-size assertion, keep invariant assertions | S7 |

**All tests must be GREEN on commit.**

---

### Commit 6 — Full Type Annotations + ANN Ruff Rules
`feat: add full type annotations to pipeline scripts and enforce ANN lint rules`

**pyproject.toml changes:**
```toml
[tool.ruff.lint]
select = ["E", "F", "I", "ANN"]
ignore = [
    "E501",   # line too long
    "F541",   # f-string without placeholders
    "F841",   # unused variables
    "I001",   # import ordering
    "ANN101", # missing type annotation for self
    "ANN102", # missing type annotation for cls
]
# F401 intentionally removed from ignore list — unused imports now flagged
```

**Files annotated (in complexity order):**

1. `01_prepare_env.py` — 4 functions
2. `07_generate_formats.py` — functions remaining after dead code removal
3. `06_add_toc.py` — medium complexity
4. `02_split_to_md.py` — complex, many functions
5. `01_convert_to_htmlz.py` — most complex
6. `03_translate_md.py` — replace `dict[str, Any]` with `RuntimeConfig` TypedDict

**Verification:** `uv run ruff check .` → 0 errors under new ANN rules proves annotation completeness.

---

### Commit 7 — Documentation Corrections
`docs: fix stale docstrings, wrong script names, and missing class docs`

**No runtime tests — human review validates:**

| File | Change |
|------|--------|
| `07_generate_formats.py:1` | Module docstring: remove `html2docx.sh`/`html2epub.sh`, describe `ebook-convert` |
| `02_split_to_md.py:705` | Error message: `01_prepare_env.py` → `01_convert_to_htmlz.py` |
| `03_translate_md.py:29` | Same script name fix |
| `06_add_toc.py:59` | Remove unreachable `not config_file` branch and stale comment |
| `ai/bilingual_merger.py` | Add class docstring: output format contract, note that `05_md_to_html.py` depends on it |
| `ai/quota_tracker.py` | Add module note: `# NOTE: QuotaTracker not yet wired into pipeline` |
| `ai/model_probe.py:64` | Add `probe()` docstring: document `last_probe_errors` side-effect attribute |
| `ai/model_selector.py:36` | Add `select()` docstring: document boundary value behavior |
| `ai/gemini_provider.py:15` | Add comment: `chunk_size` is reserved/unused, present for future rate-limiting |
| `03_translate_md.py:316` | Add comment explaining hardcoded Chinese label `markdown文件正文:` |
| `ai/epub_translate_roundtrip.py` | Add comment to `_MODEL_ALIASES`: independent from config.json alias table |

---

## Test Count Summary

| Commit | New Tests | Type |
|--------|-----------|------|
| 1 | 0 | — |
| 2 | 5 | Behavioral (pipeline_utils) |
| 3 | 4 | Behavioral (bug regression) |
| 4 | 3 | Behavioral (error handling) |
| 5 | 8 new + 2 improved | Coverage gaps + quality |
| 6 | 0 | ruff ANN check replaces runtime tests |
| 7 | 0 | — |
| **Total** | **~22** | |

## Verification Checklist (per commit)

```bash
uv run ruff check .          # 0 errors
uv run ruff format --check . # no format diffs
uv run pytest -q             # all green
bash -n translatebook.sh     # shell syntax valid
```

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| `pipeline_utils` import breaks a script | Each pipeline script's existing tests catch import failures immediately |
| `RuntimeConfig` TypedDict misses a field | `ruff check` + `mypy`-style checks catch type mismatches; `pytest` catches runtime failures |
| ANN rules produce too many false positives | `ANN101`/`ANN102` excluded; `ANN` rules applied after all annotations are complete |
| `_read_zip_text` replacement changes behavior | New test in Commit 3 pins the exact new behavior before the change lands |
| Broad except narrowing changes error propagation | New tests in Commit 4 pin error types and messages before narrowing |
