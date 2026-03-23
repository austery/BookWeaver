# PR Review Comprehensive Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 18 critical/important issues and 12 suggestions identified in the 2026-03-22 codebase review, using TDD so every behavioral change is preceded by a failing test.

**Architecture:** Seven logical commits on branch `fix/pr-review-comprehensive-cleanup`, each passing `ruff check`, `ruff format --check`, and `pytest -q`. A new root-level `pipeline_utils.py` consolidates duplicated config-loading and language-name logic from 5 pipeline scripts. Legacy scripts get full type annotations enforced by new ANN ruff rules.

**Tech Stack:** Python 3.13, pytest, ruff (linting + formatting), uv (package manager)

---

## File Map

| File | Action |
|------|--------|
| `pipeline_utils.py` | **CREATE** — shared `load_pipeline_config` + `get_language_name` |
| `tests/unit/test_pipeline_utils.py` | **CREATE** — 5 tests for pipeline_utils |
| `07_generate_formats.py` | **MODIFY** — delete dead code, fix FileNotFoundError, fix docstring |
| `01_prepare_env.py` | **MODIFY** — remove unused import, add type annotations |
| `02_split_to_md.py` | **MODIFY** — remove unused imports, fix load_config, exception chain, type annotations |
| `01_convert_to_htmlz.py` | **MODIFY** — remove Any import, narrow broad excepts, type annotations |
| `03_translate_md.py` | **MODIFY** — fix JSON loading, RuntimeConfig TypedDict, fix script name in error msg, type annotations |
| `06_add_toc.py` | **MODIFY** — use pipeline_utils, remove unreachable branch, type annotations |
| `ai/epub_translate_roundtrip.py` | **MODIFY** — fix `_read_zip_text`, add checkpoint warnings, use pipeline_utils |
| `ai/bilingual_merger.py` | **MODIFY** — add class docstring |
| `ai/quota_tracker.py` | **MODIFY** — add unused note |
| `ai/model_probe.py` | **MODIFY** — add probe() docstring |
| `ai/model_selector.py` | **MODIFY** — add select() docstring |
| `ai/gemini_provider.py` | **MODIFY** — comment chunk_size param |
| `pyproject.toml` | **MODIFY** — add ANN rules, remove F401 from ignore |
| `tests/unit/test_quota_tracker.py` | **MODIFY** — add 3 tests |
| `tests/unit/test_model_selector.py` | **MODIFY** — add 2 boundary tests |
| `tests/unit/test_translate_step3_refactor.py` | **MODIFY** — add 4 tests |
| `tests/unit/test_bilingual_merger.py` | **MODIFY** — replace manual try/except with pytest.raises |
| `tests/unit/test_epub_translate_roundtrip.py` | **MODIFY** — add 2 tests, fix brittle assertion at line 116 |
| `tests/unit/test_generate_formats_step7.py` | **MODIFY** — add 2 tests |

---

## Setup

### Task 0: Create Worktree

- [ ] **Step 1: Create an isolated git worktree**

```bash
git worktree add ../BookWeaver-cleanup -b fix/pr-review-comprehensive-cleanup
cd ../BookWeaver-cleanup
```

- [ ] **Step 2: Verify clean state**

```bash
uv run ruff check .
uv run pytest -q
```

Expected: 0 ruff errors, all tests green.

---

## Commit 1 — Dead Code Removal

### Task 1: Delete `translate_title_with_claude` and unused imports

**Files:**
- Modify: `07_generate_formats.py:36-146`
- Modify: `01_prepare_env.py:14`
- Modify: `02_split_to_md.py:13-14`
- Modify: `01_convert_to_htmlz.py:10`

**Before you delete** — record the `lang_map` from `07_generate_formats.py:47-58` for use in Task 3 (pipeline_utils language union). It has 10 entries: zh, en, ja, ko, fr, de, es, it, pt, ru.

- [ ] **Step 1: Delete `translate_title_with_claude` from `07_generate_formats.py`**

Delete lines 36–146 (the entire `translate_title_with_claude` function including its closing blank line). The function starts with `def translate_title_with_claude` and ends before `def load_config`.

- [ ] **Step 2: Remove unused `import shutil` from `01_prepare_env.py:14`**

```python
# DELETE this line:
import shutil
```

- [ ] **Step 3: Remove unused `import io` and `import json` from `02_split_to_md.py:13-14`**

```python
# DELETE these two lines:
import io
import json
```

- [ ] **Step 4: Remove unused `from typing import Any` from `01_convert_to_htmlz.py:10`**

```python
# DELETE this line:
from typing import Any
```

- [ ] **Step 5: Verify**

```bash
uv run ruff check .
uv run pytest -q
```

Expected: 0 ruff errors, all tests still green.

- [ ] **Step 6: Commit**

```bash
git add 07_generate_formats.py 01_prepare_env.py 02_split_to_md.py 01_convert_to_htmlz.py
git commit -m "chore: remove dead code and unused imports"
```

---

## Commit 2 — Shared Utilities Extraction

### Task 2: Write failing tests for `pipeline_utils`

**Files:**
- Create: `tests/unit/test_pipeline_utils.py`

- [ ] **Step 1: Create the test file**

```python
# tests/unit/test_pipeline_utils.py
from __future__ import annotations

import pytest
from pathlib import Path


def test_load_pipeline_config_returns_dict(tmp_path: Path) -> None:
    config_file = tmp_path / "config.txt"
    config_file.write_text("input_lang=en\noutput_lang=zh\nmodel=flash\n", encoding="utf-8")
    from pipeline_utils import load_pipeline_config
    result = load_pipeline_config(str(tmp_path))
    assert result["input_lang"] == "en"
    assert result["output_lang"] == "zh"
    assert result["model"] == "flash"


def test_load_pipeline_config_file_not_found(tmp_path: Path) -> None:
    from pipeline_utils import load_pipeline_config
    with pytest.raises(FileNotFoundError) as exc_info:
        load_pipeline_config(str(tmp_path))
    assert "01_convert_to_htmlz.py" in str(exc_info.value)


def test_load_pipeline_config_unicode_error(tmp_path: Path) -> None:
    config_file = tmp_path / "config.txt"
    config_file.write_bytes(b"key=\xff\xfe\n")  # invalid UTF-8
    from pipeline_utils import load_pipeline_config
    with pytest.raises(UnicodeDecodeError):
        load_pipeline_config(str(tmp_path))


def test_get_language_name_known_codes() -> None:
    from pipeline_utils import get_language_name
    assert get_language_name("zh") == "Chinese"
    assert get_language_name("en") == "English"
    assert get_language_name("ja") == "Japanese"
    assert get_language_name("fr") == "French"
    assert get_language_name("ZH") == "Chinese"  # case-insensitive


def test_get_language_name_unknown_code() -> None:
    from pipeline_utils import get_language_name
    assert get_language_name("xx") == "xx"
    assert get_language_name("UNKNOWN") == "UNKNOWN"
```

- [ ] **Step 2: Run tests to confirm RED**

```bash
uv run pytest tests/unit/test_pipeline_utils.py -v
```

Expected: `ModuleNotFoundError: No module named 'pipeline_utils'` — all 5 tests fail.

### Task 3: Create `pipeline_utils.py` to make tests GREEN

**Files:**
- Create: `pipeline_utils.py`

- [ ] **Step 1: Create `pipeline_utils.py` at root**

```python
"""
Pipeline infrastructure utilities shared by pipeline scripts.

Placed at root level (infrastructure layer) rather than inside ai/ (domain layer)
to respect Clean Architecture separation. This module will be superseded by
SPEC-007 unified YAML configuration when that work is implemented.
"""

from __future__ import annotations

import os


def load_pipeline_config(temp_dir: str) -> dict[str, str]:
    """Load pipeline config.txt written by 01_convert_to_htmlz.py.

    Args:
        temp_dir: Path to the temp directory containing config.txt.

    Returns:
        Dict of key=value pairs parsed from config.txt.

    Raises:
        FileNotFoundError: If config.txt not found. Message includes actionable hint.
        UnicodeDecodeError: If file contains non-UTF-8 bytes.
    """
    config_path = os.path.join(temp_dir, "config.txt")
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"config.txt not found in '{temp_dir}'. Run 01_convert_to_htmlz.py first."
        )
    config: dict[str, str] = {}
    with open(config_path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                config[key] = value
    return config


def get_language_name(code: str) -> str:
    """Convert ISO language code to full English name.

    Returns the code as-is if unrecognized. Case-insensitive lookup.

    Args:
        code: ISO 639-1 language code (e.g. "zh", "en").

    Returns:
        Full language name (e.g. "Chinese") or the original code if unknown.
    """
    _LANG_MAP: dict[str, str] = {
        "zh": "Chinese",
        "en": "English",
        "ja": "Japanese",
        "ko": "Korean",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "it": "Italian",
        "pt": "Portuguese",
        "ru": "Russian",
        "ar": "Arabic",
        "hi": "Hindi",
        "th": "Thai",
        "vi": "Vietnamese",
    }
    return _LANG_MAP.get(code.lower(), code)
```

- [ ] **Step 2: Run tests to confirm GREEN**

```bash
uv run pytest tests/unit/test_pipeline_utils.py -v
```

Expected: 5 tests PASS.

### Task 4: Replace duplicate implementations in pipeline scripts

**Files:**
- Modify: `02_split_to_md.py` — replace `load_config` body with import
- Modify: `03_translate_md.py` — replace `load_config` + `get_language_name` bodies with import
- Modify: `06_add_toc.py` — replace `load_config` body with import
- Modify: `07_generate_formats.py` — replace `load_config` body with import
- Modify: `ai/epub_translate_roundtrip.py` — replace `_get_language_name` with import

**How to replace each:**

**`02_split_to_md.py`** — replace the entire `load_config` function (lines 21–30) with:
```python
from pipeline_utils import load_pipeline_config as load_config  # noqa: F401
```
Add the import at the top with other imports.

Actually, since `load_config` is called throughout the file as `load_config(temp_dir)`, the cleanest approach is to import it under the same name:
```python
from pipeline_utils import load_pipeline_config
```
Then replace the `load_config` function definition with just an alias, OR rename all call sites. Use the alias approach to minimize diff:
```python
# At top of file, with other imports:
from pipeline_utils import load_pipeline_config

# Delete the existing load_config function definition entirely.
# Then update the one call site in main():
#   OLD: config = load_config(temp_dir)
#   NEW: config = load_pipeline_config(temp_dir)
```

**`03_translate_md.py`** — replace `load_config` function and `get_language_name` function:
```python
# At top with other imports:
from pipeline_utils import load_pipeline_config, get_language_name

# Delete the local load_config function (lines 24-38).
# Update call site: load_config(temp_dir) → load_pipeline_config(temp_dir)
# Delete the local get_language_name function (lines 124-142).
# (get_language_name call sites use the same name — no rename needed)
```

**`06_add_toc.py`** — replace the `load_config` function (~lines 58-80):
```python
from pipeline_utils import load_pipeline_config

# Delete local load_config function.
# Update call site: load_config(temp_dir) → load_pipeline_config(temp_dir)
```

**`07_generate_formats.py`** — **DO NOT replace `load_config`**.

The `load_config()` in `07_generate_formats.py:147` is a **zero-argument** function that glob-scans `*_temp/` directories to auto-detect the config file. Its behavior is completely different from `pipeline_utils.load_pipeline_config(temp_dir)`, which requires an explicit path. The two are not interchangeable. Leave `07_generate_formats.py:load_config` unchanged. Only `02_split_to_md.py`, `03_translate_md.py`, and `06_add_toc.py` have the compatible config-reading pattern that can be replaced.

**`ai/epub_translate_roundtrip.py`** — replace `_get_language_name` (line ~75):
```python
from pipeline_utils import get_language_name as _get_language_name

# Delete the local _get_language_name function definition.
# Call sites already use _get_language_name — no rename needed.
```

- [ ] **Step 1: Apply all 5 replacements as described above**

- [ ] **Step 2: Run full test suite**

```bash
uv run ruff check .
uv run pytest -q
```

Expected: 0 ruff errors, all tests green (including the 5 new pipeline_utils tests).

- [ ] **Step 3: Commit**

```bash
git add pipeline_utils.py tests/unit/test_pipeline_utils.py \
        02_split_to_md.py 03_translate_md.py 06_add_toc.py \
        07_generate_formats.py ai/epub_translate_roundtrip.py
git commit -m "refactor: extract pipeline_utils.py with load_pipeline_config and get_language_name"
```

---

## Commit 3 — Core Bug Fixes

### Task 5: Write 4 failing tests for core bugs

**Files:**
- Modify: `tests/unit/test_epub_translate_roundtrip.py`
- Modify: `tests/unit/test_translate_step3_refactor.py`
- Modify: `tests/unit/test_generate_formats_step7.py`

- [ ] **Step 1: Add `test_read_zip_text_missing_entry_raises_value_error` to `test_epub_translate_roundtrip.py`**

Add this test near the top of the file:

```python
def test_read_zip_text_missing_entry_raises_value_error() -> None:
    import io
    import zipfile
    from ai.epub_translate_roundtrip import _read_zip_text

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("real_file.xhtml", "<html/>")
    buf.seek(0)

    with zipfile.ZipFile(buf, "r") as zf:
        with pytest.raises(ValueError, match="EPUB missing required file"):
            _read_zip_text(zf, "does_not_exist.xhtml")
```

- [ ] **Step 2: Add `test_load_runtime_config_invalid_json_raises_with_message` to `test_translate_step3_refactor.py`**

`load_runtime_config` calls `Path.home()` which is a classmethod. Patch it by setting the attribute directly on the module-local `Path` reference using `monkeypatch.setattr`:

```python
def test_load_runtime_config_invalid_json_raises_with_message(tmp_path: Path, monkeypatch) -> None:
    module = _load_step3_module()

    # Create the user config path that load_runtime_config() looks for:
    # Path.home() / ".config" / "translatebook" / "config.json"
    config_dir = tmp_path / ".config" / "translatebook"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text("{not valid json", encoding="utf-8")

    # Patch Path.home so it returns tmp_path instead of the real home directory.
    # Path.home is a classmethod, so we patch it as a staticmethod returning tmp_path.
    import pathlib
    monkeypatch.setattr(pathlib.Path, "home", staticmethod(lambda: tmp_path))

    import json
    with pytest.raises(json.JSONDecodeError):
        module.load_runtime_config()
```

- [ ] **Step 3: Add `test_run_ebook_convert_not_installed_returns_false` to `test_generate_formats_step7.py`**

```python
def test_run_ebook_convert_not_installed_returns_false(monkeypatch, capsys) -> None:
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "step7", Path(__file__).resolve().parents[2] / "07_generate_formats.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    import subprocess
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("ebook-convert: command not found")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = module._run_ebook_convert("input.html", "output.epub")
    assert result is False
    captured = capsys.readouterr()
    assert "ebook-convert not found" in captured.out or "ebook-convert not found" in captured.err
```

- [ ] **Step 4: Add `test_checkpoint_mismatch_prints_warning` to `test_epub_translate_roundtrip.py`**

`_load_checkpoint_snapshot` accepts `checkpoint_dir: Path | None`, not a `state_file`. Internally it reads from `checkpoint_dir / "state.json"` (see `_checkpoint_state_file`). Write the state JSON there:

```python
def test_checkpoint_mismatch_prints_warning(tmp_path: Path, capsys) -> None:
    import json
    from ai.epub_translate_roundtrip import _load_checkpoint_snapshot

    # _checkpoint_state_file(checkpoint_dir) returns checkpoint_dir / "state.json"
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps({
            "source_signature": "abc123",
            "output_lang": "zh",
            "bilingual_style": "alternating",
            "model": "gemini-2.5-flash",   # ← will differ from call argument
            "custom_prompt": None,
            "completed_docs": [],
        }),
        encoding="utf-8",
    )

    # Call with a different model — should trigger mismatch warning
    _load_checkpoint_snapshot(
        checkpoint_dir=tmp_path,          # ← correct parameter name
        source_signature="abc123",
        output_lang="zh",
        bilingual_style="alternating",
        model="gemini-2.5-pro",           # ← different from checkpoint
        custom_prompt=None,
    )

    captured = capsys.readouterr()
    assert "[WARN]" in captured.out
    assert "Checkpoint invalidated" in captured.out
```

- [ ] **Step 5: Run all 4 new tests to confirm RED**

```bash
uv run pytest tests/unit/test_epub_translate_roundtrip.py::test_read_zip_text_missing_entry_raises_value_error \
               tests/unit/test_translate_step3_refactor.py::test_load_runtime_config_invalid_json_raises_with_message \
               tests/unit/test_generate_formats_step7.py::test_run_ebook_convert_not_installed_returns_false \
               tests/unit/test_epub_translate_roundtrip.py::test_checkpoint_mismatch_prints_warning \
               -v
```

Expected: all 4 FAIL.

### Task 6: Fix the 4 core bugs

**Files:**
- Modify: `ai/epub_translate_roundtrip.py:436`
- Modify: `03_translate_md.py:82-89`
- Modify: `07_generate_formats.py` (in `_run_ebook_convert`)
- Modify: `ai/epub_translate_roundtrip.py:200-234`

- [ ] **Step 1: Fix `_read_zip_text` in `ai/epub_translate_roundtrip.py`**

The hardened version already exists in `ai/epub_package.py:279-288`. Instead of copying, import it:

In `ai/epub_translate_roundtrip.py`, at the top where other imports from `ai.epub_package` exist, the file likely already imports from `epub_package`. Find that import block and add `_read_zip_text` to it, e.g.:

```python
from ai.epub_package import (
    # ... existing imports ...
    _read_zip_text,   # ADD THIS
)
```

Then delete the local `_read_zip_text` definition (the 3-line version at line ~436):
```python
# DELETE these 3 lines:
def _read_zip_text(zip_file: zipfile.ZipFile, path: str) -> str:
    raw = zip_file.read(path)
    return raw.decode("utf-8")
```

- [ ] **Step 2: Fix JSON config loading in `03_translate_md.py`**

Wrap each `json.load()` call (lines 83-84 and 87-88) with error handling:

```python
def load_runtime_config() -> dict[str, Any]:
    """Load config from bundled example and user override."""
    script_dir = Path(__file__).resolve().parent
    bundled_config_path = script_dir / "config" / "config.json.example"
    user_config_path = Path.home() / ".config" / "translatebook" / "config.json"

    config: dict[str, Any] = {}

    if bundled_config_path.exists():
        try:
            with open(bundled_config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError as exc:
            raise json.JSONDecodeError(
                f"Bundled config '{bundled_config_path}' is not valid JSON: {exc.msg}",
                exc.doc,
                exc.pos,
            ) from exc

    if user_config_path.exists():
        try:
            with open(user_config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
        except json.JSONDecodeError as exc:
            raise json.JSONDecodeError(
                f"User config '{user_config_path}' is not valid JSON — check for syntax errors: {exc.msg}",
                exc.doc,
                exc.pos,
            ) from exc
        config = _deep_merge_dict(config, user_config)
    # ... rest of function unchanged
```

- [ ] **Step 3: Fix `_run_ebook_convert` in `07_generate_formats.py`**

After the existing `except subprocess.CalledProcessError` block, add:

```python
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if isinstance(e.stderr, str) else str(e.stderr)
        log_error(f"ebook-convert failed: {stderr}")
        if e.stdout:
            log_info(f"ebook-convert output: {e.stdout}")
        return False
    except FileNotFoundError:
        log_error("ebook-convert not found. Install Calibre: https://calibre-ebook.com/")
        return False
```

- [ ] **Step 4: Add checkpoint invalidation warnings in `ai/epub_translate_roundtrip.py`**

For each of the 5 metadata mismatch branches (lines ~200-234), add a `print` before the `return`:

```python
    if raw_state.get("source_signature") != source_signature:
        print(
            f"[WARN] Checkpoint invalidated: source file changed. Starting fresh.",
            flush=True,
        )
        return CheckpointSnapshot(overrides={}, entries={}, translated_segments=0, translated_docs=0)

    if raw_state.get("output_lang") != output_lang:
        print(
            f"[WARN] Checkpoint invalidated: output_lang changed "
            f"({raw_state.get('output_lang')} -> {output_lang}). Starting fresh.",
            flush=True,
        )
        return CheckpointSnapshot(overrides={}, entries={}, translated_segments=0, translated_docs=0)

    if raw_state.get("bilingual_style") != bilingual_style:
        print(
            f"[WARN] Checkpoint invalidated: bilingual_style changed "
            f"({raw_state.get('bilingual_style')} -> {bilingual_style}). Starting fresh.",
            flush=True,
        )
        return CheckpointSnapshot(overrides={}, entries={}, translated_segments=0, translated_docs=0)

    if raw_state.get("model") != model:
        print(
            f"[WARN] Checkpoint invalidated: model changed "
            f"({raw_state.get('model')} -> {model}). Starting fresh.",
            flush=True,
        )
        return CheckpointSnapshot(overrides={}, entries={}, translated_segments=0, translated_docs=0)

    if raw_state.get("custom_prompt") != custom_prompt:
        print(
            f"[WARN] Checkpoint invalidated: custom_prompt changed. Starting fresh.",
            flush=True,
        )
        return CheckpointSnapshot(overrides={}, entries={}, translated_segments=0, translated_docs=0)
```

- [ ] **Step 5: Run the 4 tests to confirm GREEN**

```bash
uv run pytest tests/unit/test_epub_translate_roundtrip.py::test_read_zip_text_missing_entry_raises_value_error \
               tests/unit/test_translate_step3_refactor.py::test_load_runtime_config_invalid_json_raises_with_message \
               tests/unit/test_generate_formats_step7.py::test_run_ebook_convert_not_installed_returns_false \
               tests/unit/test_epub_translate_roundtrip.py::test_checkpoint_mismatch_prints_warning \
               -v
```

Expected: all 4 PASS.

- [ ] **Step 6: Run full suite**

```bash
uv run ruff check .
uv run pytest -q
```

Expected: 0 errors, all green.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_epub_translate_roundtrip.py \
        tests/unit/test_translate_step3_refactor.py \
        tests/unit/test_generate_formats_step7.py \
        ai/epub_translate_roundtrip.py \
        03_translate_md.py \
        07_generate_formats.py
git commit -m "fix: harden _read_zip_text, json config loading, ebook-convert, and checkpoint warnings"
```

---

## Commit 4 — Error Handling Improvements

### Task 7: Add 1 coverage test + 1 failing test for error handling

**Files:**
- Modify: `tests/unit/test_generate_formats_step7.py`
- Modify: `tests/unit/test_translate_step3_refactor.py`

- [ ] **Step 1: Add `test_run_ebook_convert_called_process_error_returns_false` to `test_generate_formats_step7.py`**

This is a **coverage-only test** for already-existing behavior (`CalledProcessError` handling was added in Commit 3). It should be GREEN immediately — no code change required.

```python
def test_run_ebook_convert_called_process_error_returns_false(monkeypatch, capsys) -> None:
    import importlib.util, subprocess
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "step7", Path(__file__).resolve().parents[2] / "07_generate_formats.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1, cmd="ebook-convert", stderr="Conversion error detail"
        )
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = module._run_ebook_convert("input.html", "output.epub")
    assert result is False
    captured = capsys.readouterr()
    assert "Conversion error detail" in captured.out or "Conversion error detail" in captured.err
```

- [ ] **Step 2: Run this test — expect it to PASS immediately** (existing behavior)

```bash
uv run pytest tests/unit/test_generate_formats_step7.py::test_run_ebook_convert_called_process_error_returns_false -v
```

Expected: PASS (coverage of existing code, not new behavior).

- [ ] **Step 3: Add `test_load_runtime_config_permission_error` to `test_translate_step3_refactor.py`**

```python
def test_load_runtime_config_permission_error(tmp_path: Path, monkeypatch) -> None:
    """PermissionError on user config propagates with path info."""
    module = _load_step3_module()
    config_dir = tmp_path / ".config" / "translatebook"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.json"
    config_path.write_text('{"default_model": "flash"}', encoding="utf-8")
    config_path.chmod(0o000)  # no-read

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    try:
        with pytest.raises(PermissionError):
            module.load_runtime_config()
    finally:
        config_path.chmod(0o644)  # restore so tmp_path cleanup works
```

- [ ] **Step 4: Run this test — expect RED** (current code has no PermissionError guard)

```bash
uv run pytest tests/unit/test_translate_step3_refactor.py::test_load_runtime_config_permission_error -v
```

Expected: FAIL — currently a raw `PermissionError` propagates but without path context. The test may actually pass if the OS raises `PermissionError` already. If it passes: the test is a coverage-only addition. Proceed.

### Task 8: Narrow broad `except Exception` catches

**Files:**
- Modify: `01_convert_to_htmlz.py` (7 locations)
- Modify: `02_split_to_md.py` (3 locations)

- [ ] **Step 1: Fix `01_convert_to_htmlz.py` — 7 locations**

For each location below, add a specific exception handler **before** the existing broad `except Exception`:

**Line ~62** (`convert_to_htmlz`):
```python
    except subprocess.TimeoutExpired:
        print("✗ HTMLZ conversion timed out")
        return False
    except zipfile.BadZipFile as e:
        print(f"✗ HTMLZ file appears corrupted: {e}")
        return False
    except Exception as e:
        print(f"✗ HTMLZ conversion error: {e}")
        return False
```

**Line ~127** (`extract_metadata_from_htmlz`):
```python
    except ET.ParseError as e:
        print(f"⚠️ OPF metadata file is malformed — title/author will be missing: {e}")
        return {}
    except Exception as e:
        print(f"⚠️ Error extracting metadata: {e}")
        return {}
```

**Line ~188** (`extract_htmlz`):
```python
    except zipfile.BadZipFile as e:
        print(f"✗ EPUB/HTMLZ file appears corrupted: {e}")
        return None, None
    except Exception as e:
        print(f"✗ Error extracting HTMLZ: {e}")
        return None, None
```

**Line ~222** (`setup_temp_directory`):
```python
    except OSError as e:
        print(f"✗ Error setting up temp directory (src: {input_file}): {e}")
        return None
    except Exception as e:
        print(f"✗ Error setting up temp directory: {e}")
        return None
```

**Line ~264** (`convert_html_to_markdown`):
```python
    except OSError as e:
        print(f"✗ File error during markdown conversion ({html_file}): {e}")
        return False
    except Exception as e:
        print(f"✗ Error converting HTML to markdown: {e}")
        return False
```

**Line ~358** (`split_markdown_by_size`):
```python
    except MemoryError:
        print(f"✗ Out of memory while reading large markdown file: {md_file}")
        return 0
    except OSError as e:
        print(f"✗ File error splitting markdown ({md_file}): {e}")
        return 0
    except Exception as e:
        print(f"✗ Error splitting markdown: {e}")
        return 0
```

**Line ~398** (`create_config_file`):
```python
    except OSError as e:
        print(f"✗ Error writing config file: {e}")
        return False
    except Exception as e:
        print(f"✗ Error creating config file: {e}")
        return False
```

- [ ] **Step 2: Fix `02_split_to_md.py` — 3 locations**

**`load_config` function (~line 21)** — Note: After Task 4, `load_config` was replaced with `load_pipeline_config` import. This step is already done. Skip if so.

**`convert_to_pdf_calibre` (~line 77)** — change exception re-raise to preserve chain:
```python
    except Exception as e:
        raise RuntimeError(f"ebook-convert error: {str(e)}") from e  # ADD `from e`
```

**`split_pdf_to_md` (~line 600)** — preserve stderr before exit:
```python
    except subprocess.CalledProcessError as e:
        stderr_detail = e.stderr.strip() if e.stderr else "(no stderr)"
        print(f"✗ PDF-to-markdown conversion failed: {stderr_detail}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"✗ PDF split error: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 3: Run full test suite**

```bash
uv run ruff check .
uv run pytest -q
```

Expected: 0 errors, all green.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_generate_formats_step7.py \
        tests/unit/test_translate_step3_refactor.py \
        01_convert_to_htmlz.py \
        02_split_to_md.py
git commit -m "fix: narrow broad Exception catches in 01_convert_to_htmlz.py and 02_split_to_md.py"
```

---

## Commit 5 — Test Coverage + Quality Fixes

### Task 9: Add QuotaTracker coverage tests

**Files:**
- Modify: `tests/unit/test_quota_tracker.py`

- [ ] **Step 1: Add 3 tests**

```python
def test_record_usage_negative_raises(temp_dir: Path) -> None:
    db_path = temp_dir / "quota.db"
    tracker = QuotaTracker(str(db_path))
    with pytest.raises(ValueError, match="token_count must be >= 0"):
        tracker.record_usage(model="gemini-2.5-flash", tier="flash", token_count=-1)


def test_get_daily_usage_no_records_returns_zero(temp_dir: Path) -> None:
    db_path = temp_dir / "quota.db"
    tracker = QuotaTracker(str(db_path))
    assert tracker.get_daily_usage(model="gemini-2.5-flash") == 0


def test_get_daily_usage_cross_date_isolation(temp_dir: Path) -> None:
    """Yesterday's usage must not count toward today's quota."""
    db_path = temp_dir / "quota.db"
    tracker = QuotaTracker(str(db_path))
    tracker.record_usage(model="gemini-2.5-flash", tier="flash", token_count=1000, date="2026-01-01")
    result = tracker.get_daily_usage(model="gemini-2.5-flash", date="2026-01-02")
    assert result == 0
```

- [ ] **Step 2: Run to confirm all GREEN** (behavior already exists)

```bash
uv run pytest tests/unit/test_quota_tracker.py -v
```

Expected: all PASS.

### Task 10: Add ModelSelector boundary tests

**Files:**
- Modify: `tests/unit/test_model_selector.py`

- [ ] **Step 1: Add 2 boundary tests**

```python
def test_select_at_exact_small_threshold_goes_to_medium() -> None:
    """chunk_size == small.max_chars falls through to medium (boundary is exclusive)."""
    from ai.model_selector import ModelSelector
    selector = ModelSelector(config={
        "model_thresholds": {
            "small":  {"max_chars": 5000,  "model": "small-model"},
            "medium": {"max_chars": 10000, "model": "medium-model"},
            "large":  {"max_chars": None,  "model": "large-model"},
        }
    })
    assert selector.select(chunk_size=5000) == "medium-model"


def test_select_at_exact_medium_threshold_goes_to_large() -> None:
    """chunk_size == medium.max_chars falls through to large (boundary is exclusive)."""
    from ai.model_selector import ModelSelector
    selector = ModelSelector(config={
        "model_thresholds": {
            "small":  {"max_chars": 5000,  "model": "small-model"},
            "medium": {"max_chars": 10000, "model": "medium-model"},
            "large":  {"max_chars": None,  "model": "large-model"},
        }
    })
    assert selector.select(chunk_size=10000) == "large-model"
```

- [ ] **Step 2: Run to confirm GREEN**

```bash
uv run pytest tests/unit/test_model_selector.py -v
```

### Task 11: Add translate resume + deep merge + alias cycle tests

**Files:**
- Modify: `tests/unit/test_translate_step3_refactor.py`

- [ ] **Step 1: Add 3 tests**

```python
def test_translate_files_resume_skips_existing(tmp_path: Path, monkeypatch) -> None:
    """resume=True must skip files that already have output_*.md."""
    module = _load_step3_module()

    # Create input and pre-existing output files
    input_file = tmp_path / "page0001.md"
    input_file.write_text("Some content", encoding="utf-8")
    output_file = tmp_path / "output_page0001.md"
    output_file.write_text("Already translated", encoding="utf-8")

    # translate_markdown_files calls translate_with_gemini_cli internally.
    # Monkeypatch it to track whether translation is attempted.
    translate_calls: list[str] = []

    def fake_translate_with_gemini_cli(content: str, model: str, prompt: str, **kwargs: object) -> str:
        translate_calls.append(content)
        return "translated"

    monkeypatch.setattr(module, "translate_with_gemini_cli", fake_translate_with_gemini_cli)
    monkeypatch.setattr(module, "load_runtime_config", lambda: {
        "default_model": "gemini-2.5-flash",
        "prompt_profile": "default",
        "prompt_templates": {"default": "config/prompts/default_prompt.txt"},
        "model_aliases": {},
        "fallback_chain": [],
        "model_probe": {"enabled": False},
    })

    module.translate_markdown_files(
        temp_dir=str(tmp_path),
        output_lang="zh",
        resume=True,
    )
    assert translate_calls == [], "translation should NOT be attempted for existing output file"


def test_deep_merge_dict_nested_merge() -> None:
    """Nested keys should be merged, not replaced wholesale."""
    module = _load_step3_module()
    base = {"model_thresholds": {"small": {"max_chars": 5000, "model": "flash"}}}
    override = {"model_thresholds": {"small": {"model": "pro"}}}
    result = module._deep_merge_dict(base, override)
    # The nested key should be merged, so max_chars is preserved
    assert result["model_thresholds"]["small"]["max_chars"] == 5000
    assert result["model_thresholds"]["small"]["model"] == "pro"


def test_resolve_model_alias_cycle_detection() -> None:
    """Alias cycles must raise ValueError with helpful message."""
    module = _load_step3_module()
    cyclic_config = {
        "model_aliases": {"pro": "flash", "flash": "pro"}
    }
    with pytest.raises(ValueError, match="cycle detected"):
        module.resolve_model_name("pro", runtime_config=cyclic_config)
```

- [ ] **Step 2: Run to confirm GREEN**

```bash
uv run pytest tests/unit/test_translate_step3_refactor.py -v
```

**Note:** `test_translate_files_resume_skips_existing` requires `translate_markdown_files` to accept a `translate_fn` parameter for injection. Check the actual signature — if it doesn't accept `translate_fn`, use `monkeypatch` to patch the internal translation call instead.

### Task 12: Fix test quality issues

**Files:**
- Modify: `tests/unit/test_bilingual_merger.py`
- Modify: `tests/unit/test_epub_translate_roundtrip.py:116`

- [ ] **Step 1: Replace manual try/except in `test_bilingual_merger.py`**

Replace:
```python
def test_merge_raises_on_mismatched_chunk_count():
    merger = BilingualMerger()
    try:
        merger.merge(original_chunks=["A", "B"], translated_chunks=["甲"])
    except ValueError:
        return
    raise AssertionError("Expected ValueError on mismatched chunk count")
```

With:
```python
def test_merge_raises_on_mismatched_chunk_count() -> None:
    import pytest
    merger = BilingualMerger()
    with pytest.raises(ValueError):
        merger.merge(original_chunks=["A", "B"], translated_chunks=["甲"])
```

- [ ] **Step 2: Fix brittle assertion in `test_epub_translate_roundtrip.py:116`**

Find `test_plan_segment_batches_enforces_limits_and_order` and replace the exact-size assertion:

```python
# REMOVE this line (brittle — breaks if separator chars change):
assert [len(batch) for batch in batches] == [35, 35, 35, 25]

# KEEP these (invariant-based assertions):
assert all(1 <= len(batch) <= 36 for batch in batches)
assert [item for batch in batches for item in batch] == segments
# ADD this to preserve "no data loss" intent:
assert sum(len(b) for b in batches) == len(segments)
```

- [ ] **Step 3: Run full suite**

```bash
uv run ruff check .
uv run pytest -q
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_quota_tracker.py \
        tests/unit/test_model_selector.py \
        tests/unit/test_translate_step3_refactor.py \
        tests/unit/test_bilingual_merger.py \
        tests/unit/test_epub_translate_roundtrip.py \
        tests/unit/test_generate_formats_step7.py
git commit -m "test: fill coverage gaps and improve test quality"
```

---

## Commit 6 — Full Type Annotations + ANN Ruff Rules

### Task 13: Update `pyproject.toml` to add ANN rules

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update ruff config**

Replace the `[tool.ruff.lint]` section with:

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "ANN"]
ignore = [
    "E501",   # line too long (handled by formatter)
    "F541",   # f-string without placeholders (stylistic)
    "F841",   # unused variables (acceptable in dev)
    "I001",   # import ordering (handled by formatter)
    "ANN101", # missing type annotation for self
    "ANN102", # missing type annotation for cls
]
# NOTE: F401 (unused imports) is intentionally NOT in ignore — unused imports are now errors.
```

- [ ] **Step 2: Run ruff to see all ANN violations**

```bash
uv run ruff check . 2>&1 | grep ANN | head -40
```

This shows all the annotation gaps to fix. Use this list to guide the next steps.

### Task 14: Annotate `01_prepare_env.py`

**Files:**
- Modify: `01_prepare_env.py`

- [ ] **Step 1: Add type annotations to all functions**

The file has 5 functions. Read the file first (`cat -n 01_prepare_env.py`), then add annotations:

```python
def create_temp_directory(input_file: str, clean: bool = False) -> str | None: ...
def parse_arguments() -> argparse.Namespace: ...
def validate_input_file(input_file: str) -> bool: ...
def save_config(temp_dir: str, args: argparse.Namespace, file_ext: str) -> None: ...
def main() -> None: ...
```

- [ ] **Step 2: Verify no ANN errors for this file**

```bash
uv run ruff check 01_prepare_env.py
```

### Task 15: Annotate `07_generate_formats.py`

**Files:**
- Modify: `07_generate_formats.py`

- [ ] **Step 1: Add annotations to all remaining functions**

```python
def log_info(message: str) -> None: ...
def log_success(message: str) -> None: ...
def log_error(message: str) -> None: ...
def log_warning(message: str) -> None: ...
def load_config(temp_dir: str) -> dict[str, str]: ...  # or the imported version
def parse_arguments() -> argparse.Namespace: ...
def _run_ebook_convert(html_file: str, output_file: str, metadata: dict[str, str] | None = None) -> bool: ...
def generate_docx_with_script(html_file: str, temp_dir: str, metadata: dict[str, str] | None = None) -> str | None: ...
def generate_epub_with_script(html_file: str, temp_dir: str, metadata: dict[str, str] | None = None) -> str | None: ...
def generate_pdf_with_script(html_file: str, temp_dir: str, metadata: dict[str, str] | None = None) -> str | None: ...
def main() -> None: ...
```

### Task 16: Annotate `06_add_toc.py`

**Files:**
- Modify: `06_add_toc.py`

- [ ] **Step 1: Read the file to find all unannotated functions**

```bash
grep -n "^def " 06_add_toc.py
```

- [ ] **Step 2: Add annotations to each function** (read the file to determine correct parameter types first)

Common patterns in this file:
- `soup: BeautifulSoup` for BeautifulSoup parameters
- `html_file: str` for file path parameters
- `-> str | None` for functions that may not find a value

### Task 17: Annotate `02_split_to_md.py`

**Files:**
- Modify: `02_split_to_md.py`

- [ ] **Step 1: Read the function signatures**

```bash
grep -n "^def " 02_split_to_md.py
```

- [ ] **Step 2: Add annotations** — this file has many functions including:

```python
def convert_to_pdf_calibre(input_file: str, output_file: str) -> str: ...
def split_html_by_pages(html_file: str, temp_dir: str) -> int: ...
def split_md_by_separator_with_merge(...) -> int: ...
def main() -> None: ...
```

### Task 18: Annotate `01_convert_to_htmlz.py`

**Files:**
- Modify: `01_convert_to_htmlz.py`

- [ ] **Step 1: Read the function signatures**

```bash
grep -n "^def " 01_convert_to_htmlz.py
```

- [ ] **Step 2: Add annotations** — key functions:

```python
def find_calibre_convert() -> str | None: ...
def convert_to_htmlz(input_file: str, htmlz_file: str, calibre_path: str) -> bool: ...
def extract_metadata_from_htmlz(extract_dir: str) -> dict[str, str]: ...
def extract_htmlz(htmlz_file: str, temp_dir: str) -> tuple[str | None, str | None]: ...
def setup_temp_directory(input_file: str, html_file: str, images_dir: str) -> str | None: ...
def convert_html_to_markdown(html_file: str, md_file: str) -> bool: ...
def clean_calibre_markers(content: str) -> str: ...
def split_markdown_by_size(md_file: str, temp_dir: str, target_size: int = 6000) -> int: ...
def create_config_file(temp_dir: str, input_file: str, ...) -> bool: ...
def main() -> None: ...
```

### Task 19: Add `RuntimeConfig` TypedDict to `03_translate_md.py`

**Files:**
- Modify: `03_translate_md.py`

- [ ] **Step 1: Define RuntimeConfig TypedDict**

Add after the existing imports:

```python
from typing import TypedDict


class RuntimeConfig(TypedDict, total=False):
    """Typed configuration dict for the translation pipeline runtime."""
    default_model: str
    prompt_profile: str
    prompt_templates: dict[str, str]
    model_aliases: dict[str, str]
    fallback_chain: list[str]
    model_probe: dict[str, object]
    model_thresholds: dict[str, object]
```

- [ ] **Step 2: Replace all `dict[str, Any]` with `RuntimeConfig`**

Replace every occurrence of `dict[str, Any]` in function signatures and local variables in `03_translate_md.py` with `RuntimeConfig`. Also remove `from typing import Any` (already done in Commit 1, but double-check).

- [ ] **Step 3: Run full ruff check**

```bash
uv run ruff check .
```

Expected: 0 errors (including 0 ANN errors).

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest -q
```

Expected: all green.

- [ ] **Step 5: Verify F401 is clean** (no unused imports introduced in Commits 2-5)

```bash
uv run ruff check . --select F401
```

Expected: no output (0 violations).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml \
        01_prepare_env.py 07_generate_formats.py 06_add_toc.py \
        02_split_to_md.py 01_convert_to_htmlz.py 03_translate_md.py
git commit -m "feat: add full type annotations to pipeline scripts and enforce ANN lint rules"
```

---

## Commit 7 — Documentation Corrections

### Task 20: Fix stale docstrings and wrong script names

**Files:**
- Modify: `07_generate_formats.py:1-5`
- Modify: `02_split_to_md.py:705`
- Modify: `03_translate_md.py:29`
- Modify: `06_add_toc.py:59`
- Modify: `ai/bilingual_merger.py`
- Modify: `ai/quota_tracker.py`
- Modify: `ai/model_probe.py`
- Modify: `ai/model_selector.py`
- Modify: `ai/gemini_provider.py`
- Modify: `03_translate_md.py:316`
- Modify: `ai/epub_translate_roundtrip.py` (`_MODEL_ALIASES`)

- [ ] **Step 1: Fix `07_generate_formats.py` module docstring (lines 1-5)**

```python
# REPLACE:
"""
Step 7: Generate DOCX and EPUB files in temp directory
Uses existing html2docx.sh and html2epub.sh scripts to generate files in temp directory
"""

# WITH:
"""
Step 7: Generate DOCX, EPUB, and PDF files from the bilingual HTML using Calibre ebook-convert.
"""
```

- [ ] **Step 2: Fix wrong script name in `02_split_to_md.py`**

Search for the error message referencing `01_prepare_env.py` and replace with `01_convert_to_htmlz.py`.

```bash
grep -n "01_prepare_env" 02_split_to_md.py
```

- [ ] **Step 3: Fix wrong script name in `03_translate_md.py:29`**

```python
# REPLACE:
print("Error: config.txt not found. Run 01_prepare_env.py first.")
# WITH:
print("Error: config.txt not found. Run 01_convert_to_htmlz.py first.")
```

Note: If Task 4 replaced `load_config` with `load_pipeline_config` (which raises `FileNotFoundError`), this `print + sys.exit(1)` block at line ~27-29 may already be gone. Verify — if so, skip this step.

- [ ] **Step 4: Fix `06_add_toc.py` — remove unreachable `not config_file` branch**

Find the `load_config` function (or where `pipeline_utils.load_pipeline_config` was substituted). The old code had:
```python
if not config_file or not os.path.exists(config_file):
```
Since `config_file = os.path.join(temp_dir, "config.txt")` always returns a truthy string, `not config_file` is always `False`. Remove it:
```python
if not os.path.exists(config_file):
```

- [ ] **Step 5: Add class docstring to `ai/bilingual_merger.py`**

```python
class BilingualMerger:
    """Merge original and translated text chunks into bilingual markdown.

    Output format contract:
        ## Segment N
        <original text>

        **中文译文**

        <translated text>

        ---

    IMPORTANT: The parser in 05_md_to_html.py:parse_alternating_segments depends on
    this exact format. If you change the separator markers, update the parser too.
    """
```

- [ ] **Step 6: Add unused note to `ai/quota_tracker.py`**

At the top of the file, after the module imports:
```python
# NOTE: QuotaTracker is not currently wired into the translation pipeline.
# It is reserved for future rate-limit tracking. See SPEC-007 for planned usage.
```

- [ ] **Step 7: Add `probe()` docstring to `ai/model_probe.py`**

Find the `probe` method and add:
```python
def probe(self, ...) -> dict[str, bool]:
    """Probe model availability and cache results.

    Side effect: populates self.last_probe_errors with per-model error strings
    for models that failed probing. Read this attribute immediately after calling
    probe() to get error details for unavailable models.

    Results are cached to self.cache_path for cache_ttl_seconds.
    """
```

- [ ] **Step 8: Add `select()` docstring to `ai/model_selector.py`**

```python
def select(self, chunk_size: int) -> str:
    """Select model tier based on chunk character size.

    Boundary behavior: chunk_size values equal to a tier's max_chars fall through
    to the next larger tier (comparison is strictly less-than, not less-than-or-equal).

    Examples:
        chunk_size=4999 with small.max_chars=5000 → small model
        chunk_size=5000 with small.max_chars=5000 → medium model (boundary)
    """
```

- [ ] **Step 9: Comment `chunk_size` param in `ai/gemini_provider.py`**

Find `translate_chunk` and its `chunk_size` parameter:
```python
def translate_chunk(self, text: str, chunk_size: int, ...) -> str:
    # chunk_size: reserved for future rate-limiting logic; not used by this method.
    # Callers typically pass len(text).
```

- [ ] **Step 10: Comment hardcoded Chinese label in `03_translate_md.py:316`**

Find the line with `markdown文件正文:` and add a comment:
```python
# User-turn label introducing the markdown body to translate.
# Intentionally in Chinese — this tool's primary target language.
# If supporting other primary target languages, this label should be parameterized.
f"{prompt}\n\n markdown文件正文:"
```

- [ ] **Step 11: Comment `_MODEL_ALIASES` in `ai/epub_translate_roundtrip.py`**

Find `_MODEL_ALIASES` dict and add:
```python
# EPUB-workflow-specific model aliases. These are INDEPENDENT from the model_aliases
# table in config/config.json.example (which governs the markdown pipeline in 03_translate_md.py).
# If you add an alias here, check whether config.json.example also needs updating.
_MODEL_ALIASES: dict[str, str] = {
    "pro": "gemini-2.5-pro-preview",
    ...
}
```

- [ ] **Step 12: Run full suite one final time**

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
bash -n translatebook.sh
```

Expected: 0 errors, 0 format diffs, all tests green.

- [ ] **Step 13: Commit**

```bash
git add 07_generate_formats.py 02_split_to_md.py 03_translate_md.py 06_add_toc.py \
        ai/bilingual_merger.py ai/quota_tracker.py ai/model_probe.py \
        ai/model_selector.py ai/gemini_provider.py ai/epub_translate_roundtrip.py
git commit -m "docs: fix stale docstrings, wrong script names, and missing class docs"
```

---

## Final: Merge

- [ ] **Step 1: Verify branch history looks clean**

```bash
git log --oneline main..HEAD
```

Expected: exactly 7 commits (chore, refactor, fix, fix, test, feat, docs).

- [ ] **Step 2: Push and create PR**

```bash
git push -u origin fix/pr-review-comprehensive-cleanup
gh pr create \
  --title "fix: comprehensive PR review cleanup (TDD, 7 commits)" \
  --body "Fixes all 18 critical/important issues and 12 suggestions from the 2026-03-22 codebase review.

## Summary
- Dead code removed (translate_title_with_claude + 4 unused imports)
- Shared pipeline_utils.py extracted (load_pipeline_config, get_language_name)
- Core bugs fixed (_read_zip_text KeyError, JSON config loading, ebook-convert FileNotFoundError, checkpoint warnings)
- Error handling improved (01_convert_to_htmlz.py 7 locations, 02_split_to_md.py)
- Test coverage added (~22 new/improved tests)
- Full type annotations + ANN ruff enforcement on all pipeline scripts
- 11 docstring/comment corrections

## Test plan
- [ ] All 7 commits pass ruff check + pytest -q
- [ ] No existing tests broken
- [ ] New tests cover all behavioral changes"
```
