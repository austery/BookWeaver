# SPEC-010: Terminology Extraction and Translation Constraints — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `00_extract_glossary.py` pipeline step that extracts critical technical terms from an EPUB and injects a lightweight glossary block into translation prompts to improve terminology consistency.

**Architecture:** A new `GlossaryInjector` class in `ai/glossary_injector.py` loads `extracted_glossary.json` and formats it into a `{GLOSSARY_BLOCK}` placeholder that is injected into both the markdown and EPUB translation prompts. A new `ai/glossary_extractor.py` handles calling the model and writing the JSON. Both the markdown pipeline (`03_translate_md.py`) and the EPUB roundtrip pipeline (`ai/epub_translate_roundtrip.py`) are extended with an optional `glossary_path` parameter that is a no-op when absent.

**Tech Stack:** Python 3.13, zipfile (stdlib), xml.etree.ElementTree (stdlib), existing `ai/epub_package.py` for EPUB reading, Gemini CLI/API via existing providers.

**Worktree:** `.worktrees/spec010-terminology-extraction` (branch: `feature/spec010-terminology-extraction`)

**Dev commands:**
```bash
cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/spec010-terminology-extraction
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Create | `ai/glossary_injector.py` | Load glossary JSON + format prompt block |
| Create | `ai/glossary_extractor.py` | Extract index/TOC from EPUB, call model, write JSON |
| Create | `00_extract_glossary.py` | CLI entry point for extraction step |
| Create | `config/schemas/glossary_schema.json` | Reference schema (documentation) |
| Modify | `config/prompts/ebook_prompt.txt` | Add `{GLOSSARY_BLOCK}` placeholder |
| Modify | `config/prompts/default_prompt.txt` | Add `{GLOSSARY_BLOCK}` placeholder |
| Modify | `config/config.json.example` | Add `terminology_extraction` section |
| Modify | `03_translate_md.py` | Accept `glossary_path` in `create_translation_prompt` + `translate_markdown_files` |
| Modify | `ai/epub_translate_roundtrip.py` | Accept `glossary_path` in `_create_translation_prompt` + `translate_epub_roundtrip` |
| Modify | `09_epub_translate_roundtrip.py` | Add `--glossary` CLI arg |
| Modify | `translatebook.sh` | Add `--extract-glossary` flag |
| Create | `tests/unit/test_glossary_injector.py` | Unit tests for injector |
| Create | `tests/unit/test_glossary_extractor.py` | Unit tests for extractor |
| Modify | `tests/unit/test_translate_step3_refactor.py` | Add glossary injection test |

---

## Task 1: GlossaryInjector — load and format glossary block

**Files:**
- Create: `ai/glossary_injector.py`
- Create: `tests/unit/test_glossary_injector.py`

- [ ] **Step 1.1: Write failing tests**

```python
# tests/unit/test_glossary_injector.py
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ai.glossary_injector import GlossaryInjector


MINIMAL_GLOSSARY = {
    "critical_terminology": [
        {
            "term": "Connascence",
            "suggested_translation": "共生性",
            "negative_constraint": "NOT 并发性 (Concurrency)",
            "reason": "Easily confused with Concurrency",
            "priority": "critical",
        }
    ]
}

MEDIUM_GLOSSARY = {
    "critical_terminology": [
        {
            "term": "Connascence",
            "suggested_translation": "共生性",
            "negative_constraint": "NOT 并发性 (Concurrency)",
            "reason": "Author-invented concept",
            "priority": "critical",
        },
        {
            "term": "Shift Left",
            "suggested_translation": "向左移动",
            "reason": "Architectural practice",
            "priority": "high",
        },
        {
            "term": "Evolutionary Architecture",
            "suggested_translation": "演进式架构",
            "reason": "Core book concept",
            "priority": "medium",
        },
    ]
}


def write_glossary(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "glossary.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_load_valid_glossary(tmp_path: Path) -> None:
    path = write_glossary(tmp_path, MINIMAL_GLOSSARY)
    injector = GlossaryInjector(path)
    assert len(injector.terms) == 1
    assert injector.terms[0]["term"] == "Connascence"


def test_format_block_contains_term(tmp_path: Path) -> None:
    path = write_glossary(tmp_path, MINIMAL_GLOSSARY)
    injector = GlossaryInjector(path)
    block = injector.format_block()
    assert "Connascence" in block
    assert "共生性" in block


def test_format_block_contains_negative_constraint(tmp_path: Path) -> None:
    path = write_glossary(tmp_path, MINIMAL_GLOSSARY)
    injector = GlossaryInjector(path)
    block = injector.format_block()
    assert "NOT" in block or "≠" in block


def test_format_block_empty_when_no_terms(tmp_path: Path) -> None:
    path = write_glossary(tmp_path, {"critical_terminology": []})
    injector = GlossaryInjector(path)
    assert injector.format_block() == ""


def test_format_block_under_token_budget(tmp_path: Path) -> None:
    """Block must stay lean — rough budget check via character count."""
    path = write_glossary(tmp_path, MEDIUM_GLOSSARY)
    injector = GlossaryInjector(path)
    block = injector.format_block()
    # 300 tokens ≈ 1200 characters; 20-term glossary should be well under this
    assert len(block) < 2000


def test_load_from_nonexistent_path_raises() -> None:
    with pytest.raises(FileNotFoundError):
        GlossaryInjector(Path("/nonexistent/glossary.json"))


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid glossary JSON"):
        GlossaryInjector(p)


def test_load_wrong_schema_raises(tmp_path: Path) -> None:
    p = tmp_path / "wrong.json"
    p.write_text(json.dumps({"wrong_key": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing 'critical_terminology'"):
        GlossaryInjector(p)


def test_format_block_prioritizes_critical_terms(tmp_path: Path) -> None:
    """Critical terms appear before medium-priority terms."""
    path = write_glossary(tmp_path, MEDIUM_GLOSSARY)
    injector = GlossaryInjector(path)
    block = injector.format_block()
    idx_critical = block.index("Connascence")
    idx_medium = block.index("Evolutionary Architecture")
    assert idx_critical < idx_medium
```

- [ ] **Step 1.2: Run tests to confirm they fail**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/spec010-terminology-extraction
uv run pytest tests/unit/test_glossary_injector.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError: No module named 'ai.glossary_injector'`

- [ ] **Step 1.3: Implement `ai/glossary_injector.py`**

```python
# ai/glossary_injector.py
"""Load extracted glossary JSON and format a prompt-injectable terminology block."""

from __future__ import annotations

import json
from pathlib import Path


class GlossaryInjector:
    """Loads an extracted glossary and formats it for prompt injection.

    Expected JSON schema:
        {
          "critical_terminology": [
            {
              "term": str,
              "suggested_translation": str,
              "negative_constraint": str | None,  # optional
              "reason": str | None,               # optional
              "priority": "critical" | "high" | "medium"
            }
          ]
        }
    """

    _PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2}

    def __init__(self, glossary_path: Path) -> None:
        if not glossary_path.exists():
            raise FileNotFoundError(f"Glossary file not found: {glossary_path}")
        raw = glossary_path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid glossary JSON at {glossary_path}: {exc}") from exc
        if "critical_terminology" not in data:
            raise ValueError(
                f"Glossary at {glossary_path} missing 'critical_terminology' key"
            )
        self.terms: list[dict] = sorted(
            data["critical_terminology"],
            key=lambda t: self._PRIORITY_ORDER.get(t.get("priority", "medium"), 2),
        )

    def format_block(self) -> str:
        """Return a prompt block string, or empty string if no terms."""
        if not self.terms:
            return ""
        lines: list[str] = ["【关键术语约束】以下术语必须严格遵守标准译法："]
        for entry in self.terms:
            term = entry.get("term", "")
            translation = entry.get("suggested_translation", "")
            negative = entry.get("negative_constraint", "")
            line = f"  • {term} → {translation}"
            if negative:
                line += f"（{negative}）"
            lines.append(line)
        return "\n".join(lines)
```

- [ ] **Step 1.4: Run tests to confirm they pass**

```bash
uv run pytest tests/unit/test_glossary_injector.py -v
```
Expected: All 8 tests PASS.

- [ ] **Step 1.5: Commit**

```bash
git add ai/glossary_injector.py tests/unit/test_glossary_injector.py
git commit -m "feat(spec010): add GlossaryInjector — load and format glossary block"
```

---

## Task 2: Glossary schema reference file + config extension

**Files:**
- Create: `config/schemas/glossary_schema.json`
- Modify: `config/config.json.example`

- [ ] **Step 2.1: Create `config/schemas/glossary_schema.json`**

```bash
mkdir -p config/schemas
```

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "BookWeaver Extracted Glossary",
  "description": "Output of 00_extract_glossary.py. Validated by GlossaryInjector.",
  "type": "object",
  "required": ["critical_terminology"],
  "properties": {
    "critical_terminology": {
      "type": "array",
      "maxItems": 20,
      "items": {
        "type": "object",
        "required": ["term", "suggested_translation", "priority"],
        "properties": {
          "term":                 { "type": "string" },
          "suggested_translation":{ "type": "string" },
          "negative_constraint":  { "type": "string" },
          "reason":               { "type": "string" },
          "priority":             { "type": "string", "enum": ["critical", "high", "medium"] }
        }
      }
    }
  }
}
```

- [ ] **Step 2.2: Add `terminology_extraction` section to `config/config.json.example`**

Append before the final `}`:
```json
  "terminology_extraction": {
    "enabled": false,
    "strategy": "minimal",
    "extraction_model": "gemini-2.5-pro",
    "max_terms": 20,
    "glossary_output_path": "{temp_dir}/extracted_glossary.json"
  }
```

The full `config/config.json.example` `terminology_extraction` block must be inserted as a new top-level key after `"epub_resilience"`.

- [ ] **Step 2.3: Commit**

```bash
git add config/schemas/glossary_schema.json config/config.json.example
git commit -m "feat(spec010): add glossary JSON schema + terminology_extraction config section"
```

---

## Task 3: Add `{GLOSSARY_BLOCK}` placeholder to prompt templates

**Files:**
- Modify: `config/prompts/ebook_prompt.txt`
- Modify: `config/prompts/default_prompt.txt`

The placeholder is inserted **between** the main prompt body and `{CUSTOM_INSTRUCTIONS_BLOCK}` so it takes effect before any user-supplied instructions.

- [ ] **Step 3.1: Write a failing test in an existing test file**

Open `tests/unit/test_translate_step3_refactor.py` and find the test that exercises `create_translation_prompt`. Add a new test at the bottom of the file:

```python
def test_create_translation_prompt_injects_glossary_block(tmp_path: Any) -> None:
    """GLOSSARY_BLOCK placeholder is replaced with glossary content when path given."""
    import json
    from pathlib import Path
    from unittest.mock import patch
    from ai.glossary_injector import GlossaryInjector

    glossary_data = {
        "critical_terminology": [
            {
                "term": "Connascence",
                "suggested_translation": "共生性",
                "negative_constraint": "NOT 并发性",
                "reason": "author concept",
                "priority": "critical",
            }
        ]
    }
    gpath = tmp_path / "glossary.json"
    gpath.write_text(json.dumps(glossary_data), encoding="utf-8")

    template_with_glossary = (
        "Translate to {TARGET_LANGUAGE}\n"
        "{GLOSSARY_BLOCK}\n"
        "{CUSTOM_INSTRUCTIONS_BLOCK}\n"
        "Body:"
    )
    with patch(
        "builtins.open",
        mock_open(read_data=template_with_glossary),
    ):
        prompt = create_translation_prompt("zh", glossary_path=gpath)

    assert "Connascence" in prompt
    assert "共生性" in prompt
    assert "{GLOSSARY_BLOCK}" not in prompt


def test_create_translation_prompt_glossary_block_absent_when_no_path() -> None:
    """When no glossary_path given, {GLOSSARY_BLOCK} placeholder is stripped."""
    template_with_glossary = (
        "Translate to {TARGET_LANGUAGE}\n"
        "{GLOSSARY_BLOCK}\n"
        "{CUSTOM_INSTRUCTIONS_BLOCK}\n"
        "Body:"
    )
    with patch(
        "builtins.open",
        mock_open(read_data=template_with_glossary),
    ):
        prompt = create_translation_prompt("zh")

    assert "{GLOSSARY_BLOCK}" not in prompt
```

Check the imports at the top of that file to see what's already imported (`mock_open`, `patch`, `create_translation_prompt`).

Run to confirm it fails:
```bash
uv run pytest tests/unit/test_translate_step3_refactor.py::test_create_translation_prompt_injects_glossary_block -v
```
Expected: `TypeError` — `create_translation_prompt() got an unexpected keyword argument 'glossary_path'`

- [ ] **Step 3.2: Add `{GLOSSARY_BLOCK}` to `config/prompts/ebook_prompt.txt`**

Current last two lines of the file:
```
6. 输出必须以 <!-- START --> 开始并以 <!-- END --> 结束

{CUSTOM_INSTRUCTIONS_BLOCK}
```

Replace with:
```
6. 输出必须以 <!-- START --> 开始并以 <!-- END --> 结束

{GLOSSARY_BLOCK}
{CUSTOM_INSTRUCTIONS_BLOCK}
```

- [ ] **Step 3.3: Add `{GLOSSARY_BLOCK}` to `config/prompts/default_prompt.txt`**

Current last line of the file:
```
{CUSTOM_INSTRUCTIONS_BLOCK}
```

Replace with:
```
{GLOSSARY_BLOCK}
{CUSTOM_INSTRUCTIONS_BLOCK}
```

(Add the `{GLOSSARY_BLOCK}` line immediately before `{CUSTOM_INSTRUCTIONS_BLOCK}`.)

- [ ] **Step 3.4: Modify `create_translation_prompt()` in `03_translate_md.py`**

Current signature:
```python
def create_translation_prompt(
    output_lang: str, custom_prompt: str | None = None, runtime_config: RuntimeConfig | None = None
) -> str:
```

New signature and body (show the full changed function):
```python
def create_translation_prompt(
    output_lang: str,
    custom_prompt: str | None = None,
    runtime_config: RuntimeConfig | None = None,
    glossary_path: Path | None = None,
) -> str:
    """Create translation prompt with optional glossary constraints and custom additions."""
    from pathlib import Path as _Path  # already imported at top of file; shown for clarity

    lang_name = get_language_name(output_lang)
    template = load_prompt_template(runtime_config)

    # Resolve glossary block
    glossary_block = ""
    if glossary_path is not None:
        from ai.glossary_injector import GlossaryInjector
        glossary_block = GlossaryInjector(_Path(glossary_path)).format_block()

    custom_block = f"ADDITIONAL INSTRUCTIONS:\n{custom_prompt}" if custom_prompt else ""

    prompt = template.replace("{TARGET_LANGUAGE}", lang_name)
    prompt = prompt.replace("{GLOSSARY_BLOCK}", glossary_block)

    has_custom_placeholder = "{CUSTOM_INSTRUCTIONS_BLOCK}" in prompt
    if has_custom_placeholder:
        prompt = prompt.replace("{CUSTOM_INSTRUCTIONS_BLOCK}", custom_block)
    elif custom_block:
        prompt = f"{prompt.rstrip()}\n\n{custom_block}"

    prompt = prompt.rstrip()
    return f"{prompt}\n\n markdown文件正文:"
```

**Important:** `Path` is already imported at the top of `03_translate_md.py`. Verify with `grep "^from pathlib\|^import pathlib" 03_translate_md.py`. If not present, add `from pathlib import Path` to imports.

- [ ] **Step 3.5: Run the new tests**

```bash
uv run pytest tests/unit/test_translate_step3_refactor.py -v
```
Expected: All tests in this file pass.

- [ ] **Step 3.6: Commit**

```bash
git add config/prompts/ebook_prompt.txt config/prompts/default_prompt.txt \
        03_translate_md.py \
        tests/unit/test_translate_step3_refactor.py
git commit -m "feat(spec010): add GLOSSARY_BLOCK placeholder to prompts + inject in create_translation_prompt"
```

---

## Task 4: Extend EPUB roundtrip pipeline with glossary support

**Files:**
- Modify: `ai/epub_translate_roundtrip.py`
- Modify: `09_epub_translate_roundtrip.py`
- Create: `tests/unit/test_glossary_in_epub_roundtrip.py`

- [ ] **Step 4.1: Write failing tests**

```python
# tests/unit/test_glossary_in_epub_roundtrip.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _write_glossary(tmp_path: Path) -> Path:
    data = {
        "critical_terminology": [
            {
                "term": "Connascence",
                "suggested_translation": "共生性",
                "negative_constraint": "NOT 并发性",
                "reason": "author concept",
                "priority": "critical",
            }
        ]
    }
    p = tmp_path / "glossary.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_create_translation_prompt_with_glossary(tmp_path: Path) -> None:
    """_create_translation_prompt includes glossary content when glossary provided."""
    from ai.epub_translate_roundtrip import _create_translation_prompt
    from ai.glossary_injector import GlossaryInjector

    gpath = _write_glossary(tmp_path)
    injector = GlossaryInjector(gpath)
    glossary_block = injector.format_block()

    prompt = _create_translation_prompt("zh", None, segment_count=1, glossary=glossary_block)
    assert "Connascence" in prompt
    assert "共生性" in prompt


def test_create_translation_prompt_no_glossary() -> None:
    """_create_translation_prompt works unchanged when no glossary given."""
    from ai.epub_translate_roundtrip import _create_translation_prompt

    prompt = _create_translation_prompt("zh", None, segment_count=1, glossary=None)
    assert "Connascence" not in prompt
    assert isinstance(prompt, str)
    assert len(prompt) > 0
```

Run to confirm they fail:
```bash
uv run pytest tests/unit/test_glossary_in_epub_roundtrip.py -v
```
Expected: `TypeError: _create_translation_prompt() got an unexpected keyword argument 'glossary'`

- [ ] **Step 4.2: Modify `_create_translation_prompt()` in `ai/epub_translate_roundtrip.py`**

Current:
```python
def _create_translation_prompt(
    output_lang: str,
    custom_prompt: str | None,
    *,
    segment_count: int,
) -> str:
    language_name = _get_language_name(output_lang)
    base_prompt = _IMMERSIVE_SYSTEM_PROMPT_TEMPLATE.format(target_language=language_name)

    user_prompt = _IMMERSIVE_SINGLE_PROMPT_TEMPLATE
    if segment_count > 1:
        user_prompt = _IMMERSIVE_MULTI_PROMPT_TEMPLATE
    base_prompt = f"{base_prompt}\n{user_prompt.format(target_language=language_name)}"

    if custom_prompt:
        return f"{base_prompt}\n\nADDITIONAL INSTRUCTIONS:\n{custom_prompt}"
    return base_prompt
```

New (add `glossary: str | None = None` keyword-only param):
```python
def _create_translation_prompt(
    output_lang: str,
    custom_prompt: str | None,
    *,
    segment_count: int,
    glossary: str | None = None,
) -> str:
    language_name = _get_language_name(output_lang)
    base_prompt = _IMMERSIVE_SYSTEM_PROMPT_TEMPLATE.format(target_language=language_name)

    user_prompt = _IMMERSIVE_SINGLE_PROMPT_TEMPLATE
    if segment_count > 1:
        user_prompt = _IMMERSIVE_MULTI_PROMPT_TEMPLATE
    base_prompt = f"{base_prompt}\n{user_prompt.format(target_language=language_name)}"

    if glossary:
        base_prompt = f"{base_prompt}\n\n{glossary}"
    if custom_prompt:
        return f"{base_prompt}\n\nADDITIONAL INSTRUCTIONS:\n{custom_prompt}"
    return base_prompt
```

- [ ] **Step 4.3: Thread `glossary_path` through `translate_epub_roundtrip()`**

In `ai/epub_translate_roundtrip.py`, find the `translate_epub_roundtrip()` function (the public entry point, around line 643). Add `glossary_path: Path | None = None` to its signature:

```python
def translate_epub_roundtrip(
    source_epub: Path,
    output_epub: Path,
    output_lang: str,
    bilingual_style: str,
    model: str,
    config: dict | None = None,
    provider_name: str = "cli",
    api_key: str | None = None,
    custom_prompt: str | None = None,
    translate_fn: TranslateFn | None = None,
    checkpoint_dir: Path | None = None,
    force_resume: bool = False,
    rate_limit_backoff_seconds: tuple[int, ...] | None = None,
    timeout_backoff_seconds: tuple[int, ...] | None = None,
    transient_backoff_seconds: tuple[int, ...] | None = None,
    max_split_depth: int | None = None,
    doc_failure_budget: int | None = None,
    failed_docs_path: Path | None = None,
    cli_api_fallback_enabled: bool = False,
    pro_timeout_seconds: int = _PRO_TIMEOUT_SECONDS,
    non_pro_timeout_seconds: int = _NON_PRO_TIMEOUT_SECONDS,
    glossary_path: Path | None = None,        # NEW
) -> TranslateRoundtripResult:
```

Then, near the top of the function body (before the main translation loop), add:
```python
    # Load glossary block if provided
    _glossary_block: str | None = None
    if glossary_path is not None:
        from ai.glossary_injector import GlossaryInjector
        _glossary_block = GlossaryInjector(glossary_path).format_block() or None
```

Then find all internal calls to `_create_translation_prompt(...)` in the function body (search for `_create_translation_prompt(`) and add the `glossary=_glossary_block` keyword:

```python
prompt = _create_translation_prompt(
    output_lang,
    custom_prompt,
    segment_count=len(segments),
    glossary=_glossary_block,     # ADD THIS LINE
)
```

There may be multiple call sites (batch retry path, main path). Add the kwarg to each one.

- [ ] **Step 4.4: Run the new tests**

```bash
uv run pytest tests/unit/test_glossary_in_epub_roundtrip.py -v
```
Expected: All 2 tests PASS.

- [ ] **Step 4.5: Run full test suite to check for regressions**

```bash
uv run pytest -q
```
Expected: All tests pass.

- [ ] **Step 4.6: Add `--glossary` to `09_epub_translate_roundtrip.py`**

In `parse_arguments()`, after the `-p/--prompt` argument:
```python
    parser.add_argument(
        "--glossary",
        default=None,
        help="Path to extracted glossary JSON (from 00_extract_glossary.py)",
    )
```

In `main()`, resolve the glossary path and pass it:
```python
    glossary_path = Path(args.glossary).expanduser().resolve() if args.glossary else None

    result = run_translate_roundtrip(
        source_epub=source_epub,
        output_epub=output_epub,
        output_lang=args.output_lang,
        bilingual_style=args.bilingual_style,
        model=args.model,
        config=runtime_config,
        provider_name=args.provider,
        api_key=api_key,
        custom_prompt=args.prompt,
        checkpoint_dir=checkpoint_dir,
        force_resume=args.force_resume,
        glossary_path=glossary_path,       # ADD THIS
        **resilience_overrides,
    )
```

Note: `run_translate_roundtrip` is an alias or wrapper — check if it calls `translate_epub_roundtrip` directly. If it's defined in the same file, add `glossary_path` to it too.

- [ ] **Step 4.7: Commit**

```bash
git add ai/epub_translate_roundtrip.py 09_epub_translate_roundtrip.py \
        tests/unit/test_glossary_in_epub_roundtrip.py
git commit -m "feat(spec010): thread glossary_path through EPUB roundtrip pipeline"
```

---

## Task 5: `ai/glossary_extractor.py` — extract terms from EPUB

**Files:**
- Create: `ai/glossary_extractor.py`
- Create: `tests/unit/test_glossary_extractor.py`

- [ ] **Step 5.1: Write failing tests**

```python
# tests/unit/test_glossary_extractor.py
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai.glossary_extractor import (
    extract_epub_index_and_toc,
    extract_glossary_from_epub,
    _build_extraction_prompt,
    _validate_and_parse_glossary,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_minimal_epub(tmp_path: Path, index_content: str = "", toc_content: str = "") -> Path:
    """Create a minimal valid EPUB zip for testing."""
    epub = tmp_path / "test.epub"
    container_xml = (
        '<?xml version="1.0"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf_xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:title>Test Book</dc:title></metadata>'
        '<manifest>'
        '<item id="toc" href="toc.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="idx" href="index.xhtml" media-type="application/xhtml+xml"/>'
        '</manifest>'
        '<spine toc="toc"><itemref idref="toc"/><itemref idref="idx"/></spine>'
        '</package>'
    )
    toc_xhtml = (
        '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
        f'<body><nav><ol><li>{toc_content}</li></ol></nav></body></html>'
    )
    idx_xhtml = (
        '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
        f'<body><p>{index_content}</p></body></html>'
    )
    with zipfile.ZipFile(epub, "w") as z:
        z.writestr("META-INF/container.xml", container_xml)
        z.writestr("OEBPS/content.opf", opf_xml)
        z.writestr("OEBPS/toc.xhtml", toc_xhtml)
        z.writestr("OEBPS/index.xhtml", idx_xhtml)
    return epub


# ── tests ─────────────────────────────────────────────────────────────────────

def test_extract_epub_index_and_toc_returns_text(tmp_path: Path) -> None:
    epub = _make_minimal_epub(tmp_path, index_content="Connascence, 42", toc_content="Chapter 1")
    index_text, toc_text = extract_epub_index_and_toc(epub)
    assert "Connascence" in index_text
    assert "Chapter 1" in toc_text


def test_extract_epub_index_and_toc_missing_index(tmp_path: Path) -> None:
    """If no index document found, index_text is empty string."""
    epub = _make_minimal_epub(tmp_path, toc_content="Chapter 1")
    index_text, toc_text = extract_epub_index_and_toc(epub)
    assert isinstance(index_text, str)
    assert isinstance(toc_text, str)


def test_build_extraction_prompt_contains_index_and_toc() -> None:
    prompt = _build_extraction_prompt("Connascence, 42", "Chapter 1: Intro", max_terms=15)
    assert "Connascence" in prompt
    assert "Chapter 1" in prompt
    assert "15" in prompt


def test_validate_and_parse_glossary_valid() -> None:
    raw = json.dumps({
        "critical_terminology": [
            {
                "term": "Connascence",
                "suggested_translation": "共生性",
                "priority": "critical",
            }
        ]
    })
    result = _validate_and_parse_glossary(raw)
    assert result["critical_terminology"][0]["term"] == "Connascence"


def test_validate_and_parse_glossary_strips_markdown_fence() -> None:
    raw = '```json\n{"critical_terminology": []}\n```'
    result = _validate_and_parse_glossary(raw)
    assert "critical_terminology" in result


def test_validate_and_parse_glossary_invalid_json_raises() -> None:
    with pytest.raises(ValueError, match="not valid JSON"):
        _validate_and_parse_glossary("not json at all")


def test_validate_and_parse_glossary_missing_key_raises() -> None:
    with pytest.raises(ValueError, match="missing 'critical_terminology'"):
        _validate_and_parse_glossary('{"wrong": []}')


def test_extract_glossary_from_epub_writes_json(tmp_path: Path) -> None:
    """Integration: extract_glossary_from_epub calls translate_fn and writes JSON."""
    epub = _make_minimal_epub(tmp_path, index_content="Connascence, 42", toc_content="Chapter 1")
    output_path = tmp_path / "glossary.json"
    model_response = json.dumps({
        "critical_terminology": [
            {
                "term": "Connascence",
                "suggested_translation": "共生性",
                "negative_constraint": "NOT 并发性",
                "reason": "author concept",
                "priority": "critical",
            }
        ]
    })

    mock_translate = MagicMock(return_value=model_response)

    extract_glossary_from_epub(
        epub_path=epub,
        output_path=output_path,
        translate_fn=mock_translate,
        max_terms=20,
    )

    assert output_path.exists()
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["critical_terminology"][0]["term"] == "Connascence"
```

Run to confirm they fail:
```bash
uv run pytest tests/unit/test_glossary_extractor.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'ai.glossary_extractor'`

- [ ] **Step 5.2: Implement `ai/glossary_extractor.py`**

```python
# ai/glossary_extractor.py
"""Extract critical terminology from an EPUB's Index and TOC documents.

Uses a model call (via translate_fn) to identify error-prone technical terms
and output them as a structured JSON glossary (Strategy A — minimal intervention).
"""

from __future__ import annotations

import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

from ai.epub_package import load_epub_package, _read_zip_text


# Hint strings for identifying index documents in the EPUB manifest
_INDEX_DOC_HINTS = ("index", "idx")

_EXTRACTION_PROMPT_TEMPLATE = """\
你是技术书籍翻译专家。从以下EPUB的Index和目录中提取**容易翻译错误**的关键术语。

<INDEX>
{index_content}
</INDEX>

<TOC>
{toc_content}
</TOC>

提取要求：
1. 只提取专业术语和概念（不要人名、地名、机构名）
2. 优先识别"易混淆"的术语对（拼写相似但含义不同）
3. 标注作者原创的新概念（本书首次提出的术语）
4. 最多{max_terms}条术语（聚焦最关键的术语）

严格输出以下JSON格式，不要包含任何其他文字：
{{
  "critical_terminology": [
    {{
      "term": "原文术语",
      "suggested_translation": "建议的中文翻译",
      "negative_constraint": "NOT 容易混淆的错误翻译（可选，仅在有易混淆对时填写）",
      "reason": "为什么这个术语容易翻译错误",
      "priority": "critical"
    }}
  ]
}}

priority分级：critical（作者原创/核心概念）, high（高频技术术语）, medium（重要但非核心）
"""


def _is_index_document(document_path: str | None) -> bool:
    if not document_path:
        return False
    lowered = document_path.lower()
    return any(hint in lowered for hint in _INDEX_DOC_HINTS)


def _xhtml_to_text(xhtml: str) -> str:
    """Extract plain text from XHTML, stripping all tags."""
    try:
        root = ET.fromstring(xhtml)
        return " ".join(root.itertext()).strip()
    except ET.ParseError:
        # Fallback: strip tags with regex
        return re.sub(r"<[^>]+>", " ", xhtml).strip()


def extract_epub_index_and_toc(epub_path: Path) -> tuple[str, str]:
    """Extract plain text from Index and TOC documents inside the EPUB.

    Returns:
        (index_text, toc_text) — either may be empty string if not found.
    """
    model = load_epub_package(epub_path)
    index_text = ""
    toc_text = ""

    with zipfile.ZipFile(epub_path, "r") as zf:
        opf_dir = str(Path(model.opf_path).parent)

        for item_id, item in model.manifest_items.items():
            # Resolve path relative to OPF
            item_path = str(Path(opf_dir) / item.href) if opf_dir != "." else item.href

            if _is_index_document(item.href) and not index_text:
                try:
                    raw = _read_zip_text(zf, item_path)
                    index_text = _xhtml_to_text(raw)
                except (ValueError, KeyError):
                    pass

            if model.toc_item_id and item_id == model.toc_item_id and not toc_text:
                try:
                    raw = _read_zip_text(zf, item_path)
                    toc_text = _xhtml_to_text(raw)
                except (ValueError, KeyError):
                    pass

    return index_text, toc_text


def _build_extraction_prompt(index_text: str, toc_text: str, max_terms: int) -> str:
    """Format the extraction prompt with index and TOC content."""
    return _EXTRACTION_PROMPT_TEMPLATE.format(
        index_content=index_text or "(no index found)",
        toc_content=toc_text or "(no TOC found)",
        max_terms=max_terms,
    )


def _validate_and_parse_glossary(raw_output: str) -> dict:
    """Parse and validate model output as glossary JSON.

    Strips markdown code fences if present, then validates schema.

    Raises:
        ValueError: If JSON is invalid or missing required 'critical_terminology' key.
    """
    cleaned = raw_output.strip()
    # Strip markdown code fences: ```json ... ``` or ``` ... ```
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model output is not valid JSON: {exc}\nRaw output:\n{raw_output[:200]}") from exc

    if "critical_terminology" not in data:
        raise ValueError(
            f"Model output missing 'critical_terminology' key. Got keys: {list(data.keys())}"
        )

    return data


def extract_glossary_from_epub(
    epub_path: Path,
    output_path: Path,
    translate_fn: Callable[[str], str],
    max_terms: int = 20,
) -> dict:
    """Extract terminology from EPUB and write glossary JSON to output_path.

    Args:
        epub_path: Source EPUB file.
        output_path: Where to write the extracted glossary JSON.
        translate_fn: Callable that takes a prompt string and returns model output string.
                      This is the same interface as the existing translate_chunk functions.
        max_terms: Maximum number of terms to extract (Strategy A default: 20).

    Returns:
        The parsed glossary dict.
    """
    print(f"[glossary] Extracting from: {epub_path.name}", flush=True)
    index_text, toc_text = extract_epub_index_and_toc(epub_path)
    print(
        f"[glossary] Index text: {len(index_text)} chars, TOC text: {len(toc_text)} chars",
        flush=True,
    )

    prompt = _build_extraction_prompt(index_text, toc_text, max_terms)
    raw_output = translate_fn(prompt)

    glossary = _validate_and_parse_glossary(raw_output)
    terms_count = len(glossary.get("critical_terminology", []))
    print(f"[glossary] Extracted {terms_count} terms", flush=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[glossary] Written to: {output_path}", flush=True)

    return glossary
```

- [ ] **Step 5.3: Run the extractor tests**

```bash
uv run pytest tests/unit/test_glossary_extractor.py -v
```
Expected: All 8 tests PASS.

- [ ] **Step 5.4: Run full test suite**

```bash
uv run pytest -q
```
Expected: All tests pass.

- [ ] **Step 5.5: Commit**

```bash
git add ai/glossary_extractor.py tests/unit/test_glossary_extractor.py
git commit -m "feat(spec010): add glossary_extractor — extract terms from EPUB index/toc"
```

---

## Task 6: `00_extract_glossary.py` — CLI entry point

**Files:**
- Create: `00_extract_glossary.py`

- [ ] **Step 6.1: Write the script**

```python
#!/usr/bin/env python3
# 00_extract_glossary.py
"""Pipeline step 0: Extract terminology glossary from EPUB.

Usage:
    python 00_extract_glossary.py <input.epub> --output <glossary.json> [options]

This step is optional and runs before 01_prepare_env.py. It extracts critical
technical terms from the EPUB's Index and TOC documents and writes a structured
JSON glossary that subsequent translation steps can inject into prompts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract terminology glossary from EPUB (SPEC-010 Strategy A)"
    )
    parser.add_argument("input_epub", help="Source EPUB path")
    parser.add_argument(
        "--output",
        required=True,
        help="Output glossary JSON path (e.g. {temp_dir}/extracted_glossary.json)",
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-pro",
        help="Gemini model for extraction (default: gemini-2.5-pro)",
    )
    parser.add_argument(
        "--max-terms",
        type=int,
        default=20,
        help="Maximum number of terms to extract (default: 20)",
    )
    parser.add_argument(
        "--provider",
        default="cli",
        choices=["cli", "api"],
        help="Provider to use for extraction (default: cli)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    epub_path = Path(args.input_epub).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not epub_path.exists():
        print(f"ERROR: Input EPUB not found: {epub_path}", file=sys.stderr)
        sys.exit(1)

    # Import here to avoid slow startup when not needed
    from ai.glossary_extractor import extract_glossary_from_epub

    if args.provider == "api":
        from ai.gemini_api_provider import GeminiAPIProvider
        from ai.model_probe import ModelProbe
        from03_translate_md import load_runtime_config

        runtime_config = load_runtime_config()
        api_key_env = runtime_config.get("gemini_api", {}).get("api_key")
        import os
        api_key = api_key_env or os.environ.get("GEMINI_API_KEY") or ""
        provider = GeminiAPIProvider(model=args.model, api_key=api_key)

        def translate_fn(prompt: str) -> str:
            return provider.translate_chunk(prompt, "")
    else:
        # CLI provider (default)
        from ai.gemini_provider import GeminiCLIProvider

        provider = GeminiCLIProvider(model=args.model)

        def translate_fn(prompt: str) -> str:
            return provider.translate_chunk(prompt, "")

    extract_glossary_from_epub(
        epub_path=epub_path,
        output_path=output_path,
        translate_fn=translate_fn,
        max_terms=args.max_terms,
    )


if __name__ == "__main__":
    main()
```

**Note on imports:** Check `ai/gemini_provider.py` and `ai/gemini_api_provider.py` for the correct `translate_chunk` signature. The first argument is the prompt, the second is the content (pass `""` since the extraction prompt is self-contained).

- [ ] **Step 6.2: Verify the script syntax**

```bash
uv run python -m py_compile 00_extract_glossary.py
echo "Syntax OK"
```

- [ ] **Step 6.3: Verify lint passes**

```bash
uv run ruff check 00_extract_glossary.py
```
Expected: No errors.

- [ ] **Step 6.4: Commit**

```bash
git add 00_extract_glossary.py
git commit -m "feat(spec010): add 00_extract_glossary.py CLI entry point"
```

---

## Task 7: Wire `--extract-glossary` flag in `translatebook.sh`

**Files:**
- Modify: `translatebook.sh`

- [ ] **Step 7.1: Add `EXTRACT_GLOSSARY` variable and flag parsing**

Near the top of `translatebook.sh` where other flag variables are declared (around line 18 where `CUSTOM_PROMPT=""` is set):
```bash
EXTRACT_GLOSSARY=false
GLOSSARY_PATH=""
```

In the `case` block for argument parsing (where `--workflow`, `--model`, etc. are handled), add:
```bash
            --extract-glossary)
                EXTRACT_GLOSSARY=true
                shift
                ;;
            --glossary)
                GLOSSARY_PATH="$2"
                shift 2
                ;;
```

- [ ] **Step 7.2: Update `--help` text**

In the `print_help()` function (or wherever `--workflow` and `--output-format` are documented), add:
```
    --extract-glossary     Extract terminology glossary before translation (requires EPUB input)
    --glossary PATH        Path to pre-extracted glossary JSON (skip extraction step)
```

- [ ] **Step 7.3: Add extraction step to EPUB workflow**

In the EPUB workflow section (where `09_epub_translate_roundtrip.py` is called, around line 714), add the glossary extraction step before the translate command:

```bash
        # Step 0: Glossary extraction (optional)
        local glossary_path_arg=""
        if [[ "$EXTRACT_GLOSSARY" == true ]]; then
            local glossary_output="${base_temp_dir}/extracted_glossary.json"
            log_step "workflow-epub" "Extracting terminology glossary"
            local extract_cmd=(
                python3 -u "${SCRIPT_DIR}/00_extract_glossary.py"
                "$INPUT_FILE"
                --output "$glossary_output"
                --model "${MODEL_OVERRIDE:-gemini-2.5-pro}"
                --provider "$PROVIDER"
            )
            if [[ "$DRY_RUN" == true ]]; then
                log_info "[DRY RUN] Would execute: ${extract_cmd[*]}"
            else
                "${extract_cmd[@]}" || { log_error "Glossary extraction failed"; exit 1; }
                glossary_path_arg="--glossary $glossary_output"
            fi
        elif [[ -n "$GLOSSARY_PATH" ]]; then
            glossary_path_arg="--glossary $GLOSSARY_PATH"
        fi
```

Then add `$glossary_path_arg` to the translate command (where `cmd+=(-p "$CUSTOM_PROMPT")` is):
```bash
        if [[ -n "$glossary_path_arg" ]]; then
            # shellcheck disable=SC2206
            cmd+=($glossary_path_arg)
        fi
```

- [ ] **Step 7.4: Display glossary status in dry-run summary**

Find where `echo "  Custom prompt: ..."` is printed (around line 550) and add:
```bash
    echo "  Extract glossary: ${EXTRACT_GLOSSARY}"
    echo "  Glossary path:    ${GLOSSARY_PATH:-'None'}"
```

- [ ] **Step 7.5: Verify shell syntax**

```bash
bash -n translatebook.sh
echo "Shell syntax OK"
```

- [ ] **Step 7.6: Commit**

```bash
git add translatebook.sh
git commit -m "feat(spec010): add --extract-glossary and --glossary flags to translatebook.sh"
```

---

## Task 8: Run full test suite + lint

- [ ] **Step 8.1: Run ruff lint**

```bash
uv run ruff check .
```
Expected: No errors. Fix any that appear.

- [ ] **Step 8.2: Run ruff format check**

```bash
uv run ruff format --check .
```
Expected: No formatting errors. If any, run `uv run ruff format .` and re-check.

- [ ] **Step 8.3: Run full pytest**

```bash
uv run pytest -q
```
Expected: All tests pass.

- [ ] **Step 8.4: Verify all script syntax**

```bash
bash -n translatebook.sh && \
uv run python -m py_compile 00_extract_glossary.py ai/glossary_injector.py ai/glossary_extractor.py 03_translate_md.py ai/epub_translate_roundtrip.py 09_epub_translate_roundtrip.py && \
echo "All syntax checks passed"
```

- [ ] **Step 8.5: Final commit**

```bash
git add -A
git commit -m "chore(spec010): final lint and test verification pass"
```

---

## Task 9: Update CLAUDE.md and SPEC-010 status

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/architecture/specs/SPEC-010-terminology-extraction-translation-constraints.md`

- [ ] **Step 9.1: Update CLAUDE.md**

In the "Key entrypoints" section, add:
```
- `00_extract_glossary.py` — optional pre-step: extract terminology glossary from EPUB index/toc
```

In the "Current behavior to remember" section, add:
```
- `--extract-glossary` triggers `00_extract_glossary.py` before EPUB translation; writes `{temp_dir}/extracted_glossary.json`
- `--glossary <path>` passes a pre-extracted glossary directly to the EPUB translation step
- Glossary block is injected via `{GLOSSARY_BLOCK}` placeholder in prompt templates (before `{CUSTOM_INSTRUCTIONS_BLOCK}`)
```

- [ ] **Step 9.2: Update SPEC-010 status**

Change the frontmatter:
```yaml
status: ✅ 已完成 — Strategy A MVP
lastUpdateDate: 2026-03-28
```

Mark the acceptance criteria checkboxes:
```markdown
- [x] `00_extract_glossary.py` implemented and tested
- [x] `03_translate_md.py` supports glossary injection via {GLOSSARY_BLOCK}
- [x] `ai/epub_translate_roundtrip.py` supports glossary injection
- [x] `translatebook.sh` exposes `--extract-glossary` and `--glossary` flags
- [x] Unit tests: glossary schema, prompt injection, extraction logic
- [x] Documentation: CLAUDE.md updated
```

- [ ] **Step 9.3: Commit**

```bash
git add CLAUDE.md docs/architecture/specs/SPEC-010-terminology-extraction-translation-constraints.md
git commit -m "docs(spec010): update CLAUDE.md + mark SPEC-010 Strategy A as complete"
```

---

## Spec Coverage Self-Review

| SPEC section | Covered in task |
|---|---|
| Strategy A — extract from Index + TOC only | Task 5 (`glossary_extractor.py`) |
| Max 20 terms | Task 5 (`max_terms=20` default) |
| JSON glossary schema | Task 2 |
| Glossary injection into prompt (< 300 tokens) | Task 1 (`GlossaryInjector.format_block()`) |
| `{GLOSSARY_BLOCK}` in prompt templates | Task 3 |
| `03_translate_md.py` injection | Task 3 |
| `ai/epub_translate_roundtrip.py` injection | Task 4 |
| `00_extract_glossary.py` | Task 6 |
| `--extract-glossary` CLI flag | Task 7 |
| Unit tests | Tasks 1, 4, 5 |
| Config section | Task 2 |
| CLAUDE.md + SPEC status | Task 9 |
| Negative constraints in block | Task 1 (format uses `NOT ...` notation) |
| Fallback: empty glossary → no-op | Task 1 (`format_block()` returns `""`) |
| Priority ordering (critical first) | Task 1 (sorted by `_PRIORITY_ORDER`) |

No gaps identified.
