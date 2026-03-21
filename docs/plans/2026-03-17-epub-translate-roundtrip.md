# EPUB Translate Roundtrip Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an optional package-aware EPUB translation mode that outputs bilingual alternating EPUB while preserving structure and navigation integrity.

**Architecture:** Keep the existing default markdown pipeline untouched. Add a new flag-driven branch that translates spine XHTML body text nodes, patches bilingual alternating content, validates integrity strictly, and repacks directly from source EPUB package data.

**Tech Stack:** Python 3.13, `zipfile`, `xml.etree.ElementTree`, `subprocess` (Gemini CLI), `pytest`, `uv`, shell orchestration in `translatebook.sh`

---

### Task 1: Add failing CLI contract tests for translate roundtrip mode

**Files:**
- Modify: `tests/unit/test_epub_baseline_cli.py`
- Test: `tests/unit/test_epub_baseline_cli.py`

**Step 1: Write the failing test**

```python
def test_translatebook_help_includes_epub_translate_roundtrip_mode() -> None:
    content = Path("translatebook.sh").read_text(encoding="utf-8")
    assert "--epub-translate-roundtrip" in content


def test_translate_roundtrip_script_exists() -> None:
    assert Path("09_epub_translate_roundtrip.py").exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_baseline_cli.py -v`  
Expected: FAIL (`--epub-translate-roundtrip` and script missing).

**Step 3: Write minimal implementation**

No implementation in this task. Keep tests red.

**Step 4: Re-run to keep red baseline**

Run: `uv run pytest -q tests/unit/test_epub_baseline_cli.py -v`  
Expected: FAIL.

**Step 5: Commit**

```bash
git add tests/unit/test_epub_baseline_cli.py
git commit -m "test: add failing cli checks for epub translate roundtrip mode"
```

### Task 2: Add failing XHTML bilingual patcher tests

**Files:**
- Create: `tests/unit/test_epub_translate_patcher.py`
- Test: `tests/unit/test_epub_translate_patcher.py`

**Step 1: Write the failing test**

```python
def test_patch_xhtml_with_alternating_bilingual_keeps_anchor_ids() -> None:
    from ai.epub_package import patch_xhtml_alternating

    source = "<html xmlns='http://www.w3.org/1999/xhtml'><body><p id='p1'>Hello.</p></body></html>"
    patched = patch_xhtml_alternating(source, translations=["你好。"])
    assert "id=\"p1\"" in patched
    assert "Hello." in patched
    assert "你好。" in patched


def test_patch_xhtml_alternating_requires_matching_translation_count() -> None:
    from ai.epub_package import extract_translatable_segments, patch_xhtml_alternating

    source = "<html xmlns='http://www.w3.org/1999/xhtml'><body><p>Hello.</p></body></html>"
    segments = extract_translatable_segments(source)
    assert len(segments) == 1
    with pytest.raises(ValueError, match="translation count"):
        patch_xhtml_alternating(source, translations=[])
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_patcher.py -v`  
Expected: FAIL (functions missing).

**Step 3: Write minimal implementation**

No implementation in this task. Keep tests red.

**Step 4: Re-run to keep red baseline**

Run: `uv run pytest -q tests/unit/test_epub_translate_patcher.py -v`  
Expected: FAIL.

**Step 5: Commit**

```bash
git add tests/unit/test_epub_translate_patcher.py
git commit -m "test: add failing xhtml alternating patcher tests"
```

### Task 3: Implement XHTML extraction + alternating patcher primitives

**Files:**
- Modify: `ai/epub_package.py`
- Test: `tests/unit/test_epub_translate_patcher.py`

**Step 1: Run failing tests**

Run: `uv run pytest -q tests/unit/test_epub_translate_patcher.py -v`  
Expected: FAIL.

**Step 2: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class TranslatableSegment:
    text: str

def extract_translatable_segments(xhtml: str) -> list[TranslatableSegment]:
    ...

def patch_xhtml_alternating(xhtml: str, translations: list[str]) -> str:
    ...
```

Implementation constraints:
- Extract only non-empty body text segments intended for translation.
- Preserve existing ids/classes/hrefs and element order.
- On count mismatch, raise explicit `ValueError`.

**Step 3: Run tests to verify pass**

Run: `uv run pytest -q tests/unit/test_epub_translate_patcher.py -v`  
Expected: PASS.

**Step 4: Run related package tests**

Run: `uv run pytest -q tests/unit/test_epub_package_model.py tests/unit/test_epub_integrity_checks.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add ai/epub_package.py tests/unit/test_epub_translate_patcher.py
git commit -m "feat: add xhtml segment extraction and alternating patching primitives"
```

### Task 4: Add failing translate-roundtrip workflow tests

**Files:**
- Create: `tests/unit/test_epub_translate_roundtrip.py`
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Write the failing test**

```python
def test_translate_roundtrip_rewrites_spine_xhtml_and_preserves_toc_file():
    from ai.epub_translate_roundtrip import run_translate_roundtrip
    ...
    result = run_translate_roundtrip(...)
    assert result.output_epub.exists()
    assert result.translated_segments > 0
    assert toc_before == toc_after
```

```python
def test_translate_roundtrip_fails_on_integrity_error():
    from ai.epub_translate_roundtrip import run_translate_roundtrip
    with pytest.raises(RuntimeError, match="broken fragment"):
        run_translate_roundtrip(...)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -v`  
Expected: FAIL (`ai.epub_translate_roundtrip` missing).

**Step 3: Write minimal implementation**

No implementation in this task. Keep tests red.

**Step 4: Re-run to keep red baseline**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -v`  
Expected: FAIL.

**Step 5: Commit**

```bash
git add tests/unit/test_epub_translate_roundtrip.py
git commit -m "test: add failing workflow tests for epub translate roundtrip"
```

### Task 5: Implement translate-roundtrip engine and CLI entry script

**Files:**
- Create: `ai/epub_translate_roundtrip.py`
- Create: `09_epub_translate_roundtrip.py`
- Modify: `ai/epub_package.py` (helper exports if needed)
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Run failing workflow tests**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -v`  
Expected: FAIL.

**Step 2: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class TranslateRoundtripResult:
    output_epub: Path
    translated_segments: int
    translated_docs: int

def run_translate_roundtrip(...)->TranslateRoundtripResult:
    # load package, translate spine docs, patch alternating, validate, repack
    ...
```

```python
# 09_epub_translate_roundtrip.py
def main() -> None:
    # parse args and execute run_translate_roundtrip
    ...
```

Implementation requirements:
- Keep nav/toc files untouched.
- Strict fail-fast on integrity validation failures.
- Use existing Gemini CLI provider path for translation calls.

**Step 3: Run workflow tests to verify pass**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -v`  
Expected: PASS.

**Step 4: Run focused integration command**

Run:

```bash
uv run python 09_epub_translate_roundtrip.py tmp/Psycho-Cybernetics.epub \
  --output tmp/Psycho-Cybernetics.translated-roundtrip.epub \
  --output-lang zh --bilingual-style alternating
```

Expected: output EPUB exists, summary reports translated docs/segments.

**Step 5: Commit**

```bash
git add ai/epub_translate_roundtrip.py 09_epub_translate_roundtrip.py ai/epub_package.py
git commit -m "feat: add package-aware epub translate roundtrip engine and cli"
```

### Task 6: Wire translate-roundtrip mode into orchestrator

**Files:**
- Modify: `translatebook.sh`
- Modify: `tests/unit/test_epub_baseline_cli.py`
- Test: `tests/unit/test_epub_baseline_cli.py`

**Step 1: Add failing flag-wiring test**

```python
def test_translatebook_wires_epub_translate_roundtrip_flag() -> None:
    content = Path("translatebook.sh").read_text(encoding="utf-8")
    assert "--epub-translate-roundtrip" in content
    assert "09_epub_translate_roundtrip.py" in content
```

**Step 2: Run test to verify fail**

Run: `uv run pytest -q tests/unit/test_epub_baseline_cli.py -v`  
Expected: FAIL before wiring.

**Step 3: Implement shell wiring**

```bash
--epub-translate-roundtrip) EPUB_TRANSLATE_ROUNDTRIP=true ;;

if [[ "$EPUB_TRANSLATE_ROUNDTRIP" == true ]]; then
  python3 "${SCRIPT_DIR}/09_epub_translate_roundtrip.py" \
    "$INPUT_FILE" \
    --output "${base_temp_dir}/translated_roundtrip.epub" \
    --output-lang "$OUTPUT_LANG" \
    --bilingual-style "$BILINGUAL_STYLE" \
    --model "${MODEL_OVERRIDE:-}"
  exit 0
fi
```

**Step 4: Re-run tests**

Run: `uv run pytest -q tests/unit/test_epub_baseline_cli.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add translatebook.sh tests/unit/test_epub_baseline_cli.py
git commit -m "feat: wire epub translate roundtrip mode into orchestrator"
```

### Task 7: Docs updates and full verification

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Create: `docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md`

**Step 1: Add docs checks (failing state)**

Run: `rg -n "epub-translate-roundtrip|translated_roundtrip|SPEC-006" README.md CLAUDE.md docs/architecture/specs`  
Expected: missing entries initially.

**Step 2: Add docs**

Include:
- new mode command examples
- strict integrity fail policy
- alternating-only support in phase 1
- E2E checklist (cover/TOC/anchors/resources)

**Step 3: Re-run docs check**

Run: `rg -n "epub-translate-roundtrip|translated_roundtrip|SPEC-006" README.md CLAUDE.md docs/architecture/specs`  
Expected: matches in all docs.

**Step 4: Full verification**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
bash -n translatebook.sh
uv run python -m py_compile 09_epub_translate_roundtrip.py ai/epub_translate_roundtrip.py ai/epub_package.py
```

Expected: all checks pass.

**Step 5: Commit**

```bash
git add README.md CLAUDE.md docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md
git commit -m "docs: add epub translate roundtrip mode spec and usage"
```
