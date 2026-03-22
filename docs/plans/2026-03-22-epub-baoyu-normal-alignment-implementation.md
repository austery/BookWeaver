# EPUB Baoyu-Normal Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make EPUB context-pass artifacts (`01-analysis.md`, `02-prompt.md`) strictly follow Baoyu normal workflow semantics, including auto audience/style presets with CLI overrides.

**Architecture:** Keep EPUB-first pipeline and reuse current context doc selection/sampling. Replace simplified analysis/prompt rendering with a Baoyu-structured analysis model plus template-based prompt assembly. Add deterministic preset resolver (auto + override precedence) and persist reasoning into analysis/manifest so translation prompt generation is inspectable and reproducible.

**Tech Stack:** Python 3.13, pytest, Ruff, existing EPUB pipeline (`ai/epub_translate_roundtrip.py`, `ai/epub_context_pass.py`), CLI entrypoints (`09_epub_translate_roundtrip.py`, `translatebook.sh`).

---

### Task 1: Add audience/style CLI contract and plumbing

**Files:**
- Modify: `09_epub_translate_roundtrip.py`
- Modify: `translatebook.sh`
- Modify: `ai/epub_translate_roundtrip.py`
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Write the failing test**

```python
def test_epub_roundtrip_accepts_audience_and_style_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_roundtrip_cli_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "09_epub_translate_roundtrip.py",
            "book.epub",
            "--output",
            "translated.epub",
            "--audience",
            "technical",
            "--style",
            "technical",
        ],
    )
    args = module.parse_arguments()
    assert args.audience == "technical"
    assert args.style == "technical"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_epub_roundtrip_accepts_audience_and_style_flags`
Expected: FAIL (`unrecognized arguments: --audience --style`)

**Step 3: Write minimal implementation**

```python
# 09_epub_translate_roundtrip.py
parser.add_argument("--audience", default=None)
parser.add_argument("--style", default=None)

# run_translate_roundtrip(...)
audience=args.audience,
style=args.style,
```

Wire flag passthrough in `translatebook.sh` for EPUB path.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_epub_roundtrip_accepts_audience_and_style_flags`
Expected: PASS

**Step 5: Commit**

```bash
git add 09_epub_translate_roundtrip.py translatebook.sh ai/epub_translate_roundtrip.py tests/unit/test_epub_translate_roundtrip.py
git commit -m "feat: add epub audience and style cli overrides"
```

---

### Task 2: Implement deterministic preset resolver (auto + reason)

**Files:**
- Create: `ai/epub_preset_resolver.py`
- Test: `tests/unit/test_epub_preset_resolver.py`

**Step 1: Write failing tests**

```python
def test_resolve_presets_technical_content_prefers_technical() -> None:
    resolved = resolve_presets(
        sampled_text=["API schema", "distributed system", "latency budget"],
        audience_override=None,
        style_override=None,
    )
    assert resolved.audience == "technical"
    assert resolved.style == "technical"
    assert "technical signal" in resolved.audience_reason.lower()


def test_resolve_presets_philosophy_content_prefers_general_storytelling() -> None:
    resolved = resolve_presets(
        sampled_text=["Stoic", "virtue", "meaning of life"],
        audience_override=None,
        style_override=None,
    )
    assert resolved.audience == "general"
    assert resolved.style == "storytelling"


def test_resolve_presets_override_wins_and_is_marked() -> None:
    resolved = resolve_presets(
        sampled_text=["API schema"],
        audience_override="business",
        style_override="formal",
    )
    assert resolved.audience == "business"
    assert resolved.style == "formal"
    assert resolved.audience_source == "cli_override"
    assert resolved.style_source == "cli_override"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/unit/test_epub_preset_resolver.py`
Expected: FAIL (`ModuleNotFoundError`)

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class ResolvedPresets:
    audience: str
    style: str
    audience_reason: str
    style_reason: str
    audience_source: str  # auto|cli_override
    style_source: str     # auto|cli_override

# deterministic keyword scoring + fallback general/storytelling
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/unit/test_epub_preset_resolver.py`
Expected: PASS

**Step 5: Commit**

```bash
git add ai/epub_preset_resolver.py tests/unit/test_epub_preset_resolver.py
git commit -m "feat: add deterministic epub audience/style preset resolver"
```

---

### Task 3: Build Baoyu-structured analysis model and renderer

**Files:**
- Create: `ai/epub_baoyu_analysis.py`
- Modify: `ai/epub_context_pass.py`
- Test: `tests/unit/test_epub_baoyu_analysis.py`

**Step 1: Write failing tests**

```python
def test_render_analysis_contains_required_baoyu_sections() -> None:
    text = render_analysis_markdown(example_analysis())
    for heading in [
        "## Quick Summary",
        "## Core Content",
        "## Background Context",
        "## Terminology",
        "## Tone & Style",
        "## Comprehension Challenges",
        "## Figurative Language & Metaphor Mapping",
        "## Structural & Creative Challenges",
        "## Preset Resolution",
    ]:
        assert heading in text


def test_preset_resolution_section_contains_reason_and_source() -> None:
    text = render_analysis_markdown(example_analysis())
    assert "Audience:" in text
    assert "Style:" in text
    assert "Reason:" in text
    assert "Source:" in text
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/unit/test_epub_baoyu_analysis.py`
Expected: FAIL (`ModuleNotFoundError`)

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class BaoyuAnalysis:
    quick_summary: list[str]
    core_argument: str
    key_concepts: list[str]
    structure: list[str]
    background_context: list[str]
    terminology: list[tuple[str, str]]
    tone_style_assessment: list[str]
    comprehension_challenges: list[tuple[str, str, str]]
    figurative_mapping: list[tuple[str, str, str, str]]
    structural_challenges: list[str]
    preset_resolution: PresetResolution
```

Render exact required section headings and deterministic order.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/unit/test_epub_baoyu_analysis.py`
Expected: PASS

**Step 5: Commit**

```bash
git add ai/epub_baoyu_analysis.py ai/epub_context_pass.py tests/unit/test_epub_baoyu_analysis.py
git commit -m "feat: add baoyu-structured analysis rendering for epub context pass"
```

---

### Task 4: Build Baoyu-template prompt assembler

**Files:**
- Create: `ai/epub_baoyu_prompt.py`
- Modify: `ai/epub_context_pass.py`
- Test: `tests/unit/test_epub_baoyu_prompt.py`

**Step 1: Write failing tests**

```python
def test_render_prompt_contains_required_template_sections() -> None:
    prompt = render_prompt_markdown(example_prompt_model())
    required = [
        "## Target Audience",
        "## Translation Style",
        "## Content Background",
        "## Glossary",
        "## Comprehension Challenges",
        "## Translation Principles",
    ]
    for heading in required:
        assert heading in prompt


def test_prompt_inlines_analysis_background_and_glossary() -> None:
    prompt = render_prompt_markdown(example_prompt_model())
    assert "Core argument" in prompt
    assert "API → 接口" in prompt
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/unit/test_epub_baoyu_prompt.py`
Expected: FAIL (`ModuleNotFoundError`)

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class PromptModel:
    target_lang: str
    audience_description: str
    style_description: str
    content_background_lines: list[str]
    glossary_lines: list[str]
    comprehension_lines: list[str]
```

Render template sections in fixed order; avoid freeform drift.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/unit/test_epub_baoyu_prompt.py`
Expected: PASS

**Step 5: Commit**

```bash
git add ai/epub_baoyu_prompt.py ai/epub_context_pass.py tests/unit/test_epub_baoyu_prompt.py
git commit -m "feat: add baoyu-template prompt assembly for epub"
```

---

### Task 5: Integrate resolver + analysis + prompt into context pass

**Files:**
- Modify: `ai/epub_context_pass.py`
- Modify: `ai/epub_translate_roundtrip.py`
- Modify: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Write failing integration-oriented tests**

```python
def test_context_pass_records_auto_resolved_presets_in_analysis() -> None:
    # run context pass with no overrides
    assert "## Preset Resolution" in analysis_text
    assert "Audience:" in analysis_text
    assert "Style:" in analysis_text


def test_context_pass_cli_override_has_priority_and_is_recorded() -> None:
    # pass audience/style override
    assert "Audience: business" in analysis_text
    assert "Source: cli_override" in analysis_text


def test_generated_prompt_uses_baoyu_template_sections() -> None:
    assert "## Target Audience" in prompt_text
    assert "## Translation Principles" in prompt_text
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -k "preset_resolution or baoyu_template_sections"`
Expected: FAIL

**Step 3: Write minimal implementation**

- In `run_translate_roundtrip(...)`, pass `audience`, `style` into context-pass builder.
- In `run_epub_context_pass(...)`, run resolver, generate structured analysis model, generate template prompt.
- Write `context_manifest.json` additional fields:

```json
{
  "resolved_audience": "...",
  "resolved_style": "...",
  "audience_source": "auto|cli_override",
  "style_source": "auto|cli_override"
}
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -k "preset_resolution or baoyu_template_sections or context_pass_writes_analysis_prompt_and_manifest or uses_context_prompt"`
Expected: PASS

**Step 5: Commit**

```bash
git add ai/epub_context_pass.py ai/epub_translate_roundtrip.py tests/unit/test_epub_translate_roundtrip.py
git commit -m "feat: align epub context pass with baoyu normal analysis and prompt workflow"
```

---

### Task 6: Update docs and user-facing contract

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md`

**Step 1: Write doc assertions test (optional lightweight grep-based check in test or script)**

```python
def test_docs_mention_audience_style_overrides_and_baoyu_sections() -> None:
    # optional if repo has docs checks; otherwise skip and verify manually
```

**Step 2: Verify docs currently missing/incorrect**

Run:

```bash
grep -n "--audience\|--style\|Preset Resolution\|Target Audience" README.md docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md
```

Expected: Missing or incomplete Baoyu-normal contract references.

**Step 3: Write minimal documentation updates**

- Add CLI examples for `--audience`, `--style`
- Document auto inference + override precedence
- Document required `01/02` section contracts

**Step 4: Verify docs updated**

Run:

```bash
grep -n "--audience\|--style\|Preset Resolution\|Target Audience" README.md docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md
```

Expected: Matches found in both files.

**Step 5: Commit**

```bash
git add README.md docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md
git commit -m "docs: document baoyu-normal epub preset and prompt contracts"
```

---

### Task 7: Full verification + Roman Emperor artifact validation

**Files:**
- Verify: whole repo changes in this branch

**Step 1: Run focused tests first**

Run:

```bash
uv run pytest -q tests/unit/test_epub_preset_resolver.py tests/unit/test_epub_baoyu_analysis.py tests/unit/test_epub_baoyu_prompt.py tests/unit/test_epub_translate_roundtrip.py
```

Expected: PASS

**Step 2: Run full quality gates (@verification-before-completion)**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
bash -n translatebook.sh
```

Expected: all pass.

**Step 3: Run real artifact generation command on Roman Emperor EPUB**

Run a prompt-generation command that outputs:

- `tmp/epub_orchestration_roman_emperor/01-analysis.md`
- `tmp/epub_orchestration_roman_emperor/02-prompt.md`

Then verify section headers exist:

```bash
grep -n "## Preset Resolution\|## Figurative Language & Metaphor Mapping" tmp/epub_orchestration_roman_emperor/01-analysis.md
grep -n "## Target Audience\|## Translation Style\|## Translation Principles" tmp/epub_orchestration_roman_emperor/02-prompt.md
```

Expected: all required headings present.

**Step 4: Final commit**

```bash
git add ai/epub_preset_resolver.py ai/epub_baoyu_analysis.py ai/epub_baoyu_prompt.py ai/epub_context_pass.py ai/epub_translate_roundtrip.py 09_epub_translate_roundtrip.py translatebook.sh tests/unit/test_epub_preset_resolver.py tests/unit/test_epub_baoyu_analysis.py tests/unit/test_epub_baoyu_prompt.py tests/unit/test_epub_translate_roundtrip.py README.md docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md
git commit -m "feat: align epub context artifacts with baoyu normal workflow"
```

---

## Execution status update (archived)

- Task1-3 was partially executed and validated in this feature branch.
- Exploratory A/B signal was collected on Roman Emperor first two chapters.
- Product decision: stop dynamic rollout and archive this track; no further implementation tasks are required for `main`.
