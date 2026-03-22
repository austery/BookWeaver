# EPUB-First Context Pass Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an EPUB-first context pass to `--epub-translate-roundtrip` so the system builds global book understanding (`TOC + Preface + Chapter 1`) before translating the full spine with one shared prompt.

**Architecture:** Extend `ai/epub_translate_roundtrip.py` with a deterministic context pipeline: select representative EPUB docs, sample paragraphs under agreed budget, generate `01-analysis.md` + `02-prompt.md` + manifest, then reuse that prompt in translation. Keep existing repack/segment patch/checkpoint mechanisms, with checkpoint compatibility extended by context signature and prompt hash.

**Tech Stack:** Python 3.13, pytest, Ruff, existing EPUB package parser (`ai/epub_package.py`), roundtrip engine (`ai/epub_translate_roundtrip.py`), BookWeaver CLI (`09_epub_translate_roundtrip.py`, `translatebook.sh`).

---

### Task 1: Add Context Config and CLI Surface

**Files:**
- Modify: `09_epub_translate_roundtrip.py:11-56`
- Modify: `translatebook.sh` (epub translate roundtrip arg forwarding)
- Test: `tests/unit/test_translate_step3_refactor.py` (only if shared arg parsing helper touched; otherwise skip)
- Create/Modify: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Write the failing test**

```python
def test_epub_roundtrip_accepts_context_pass_flags() -> None:
    # parse args includes:
    # --context-pass-mode auto|off
    # --force-context-rebuild
    # --context-max-paragraphs-per-doc
    # --context-max-paragraphs-total
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_epub_roundtrip_accepts_context_pass_flags`
Expected: FAIL (flags not recognized).

**Step 3: Write minimal implementation**

```python
parser.add_argument("--context-pass-mode", default="auto", choices=["auto", "off"])
parser.add_argument("--force-context-rebuild", action="store_true")
parser.add_argument("--context-max-paragraphs-per-doc", type=int, default=8)
parser.add_argument("--context-max-paragraphs-total", type=int, default=120)
```

Wire through `run_translate_roundtrip(...)`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_epub_roundtrip_accepts_context_pass_flags`
Expected: PASS.

**Step 5: Commit**

```bash
git add 09_epub_translate_roundtrip.py translatebook.sh tests/unit/test_epub_translate_roundtrip.py
git commit -m "feat: add epub context-pass cli contract"
```

### Task 2: Implement Context Doc Selection (TOC + Preface + Ch1)

**Files:**
- Modify: `ai/epub_translate_roundtrip.py`
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Write the failing test**

```python
def test_select_context_docs_prefers_toc_preface_ch1() -> None:
    selected = _select_context_docs(...)
    assert selected == ["toc.xhtml", "preface.xhtml", "chapter1.xhtml"]
```

Include fallback test when preface missing.

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_select_context_docs_prefers_toc_preface_ch1`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
def _select_context_docs(...)->list[str]:
    # deterministic heuristics:
    # toc -> preface-like -> first chapter-like in spine order
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -k "select_context_docs"`
Expected: PASS.

**Step 5: Commit**

```bash
git add ai/epub_translate_roundtrip.py tests/unit/test_epub_translate_roundtrip.py
git commit -m "feat: add deterministic epub context doc selection"
```

### Task 3: Implement Paragraph Sampling Budget (8 per doc, 120 total)

**Files:**
- Modify: `ai/epub_translate_roundtrip.py`
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Write the failing test**

```python
def test_context_sampling_enforces_per_doc_and_global_limits() -> None:
    sampled = _sample_context_paragraphs(...)
    assert max(count_by_doc.values()) <= 8
    assert sum(count_by_doc.values()) <= 120
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_context_sampling_enforces_per_doc_and_global_limits`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
def _sample_context_paragraphs(...)->list[ContextParagraph]:
    # preserve doc order and paragraph order
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -k "context_sampling"`
Expected: PASS.

**Step 5: Commit**

```bash
git add ai/epub_translate_roundtrip.py tests/unit/test_epub_translate_roundtrip.py
git commit -m "feat: enforce epub context sampling budget"
```

### Task 4: Build Context Artifacts (`01/02/manifest`)

**Files:**
- Modify: `ai/epub_translate_roundtrip.py`
- Create: `ai/epub_context_pass.py`
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Write the failing test**

```python
def test_context_pass_writes_analysis_prompt_and_manifest(tmp_path):
    artifacts = run_context_pass(...)
    assert (artifacts_dir / "01-analysis.md").exists()
    assert (artifacts_dir / "02-prompt.md").exists()
    assert (artifacts_dir / "context_manifest.json").exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_context_pass_writes_analysis_prompt_and_manifest`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class EpubContextArtifacts:
    analysis_path: Path
    prompt_path: Path
    manifest_path: Path
    context_signature: str
    prompt_hash: str
```

Use deterministic analysis/prompt composition for iteration-1.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -k "context_pass_writes_analysis_prompt_and_manifest"`
Expected: PASS.

**Step 5: Commit**

```bash
git add ai/epub_context_pass.py ai/epub_translate_roundtrip.py tests/unit/test_epub_translate_roundtrip.py
git commit -m "feat: add epub context artifacts generation"
```

### Task 5: Reuse Shared Prompt in Translation Pass

**Files:**
- Modify: `ai/epub_translate_roundtrip.py`
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Write the failing test**

```python
def test_roundtrip_uses_context_prompt_instead_of_inline_immersive_template() -> None:
    # spy translate_fn input prompt path/hash usage
    assert used_prompt_text == generated_prompt_text
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py::test_roundtrip_uses_context_prompt_instead_of_inline_immersive_template`
Expected: FAIL.

**Step 3: Write minimal implementation**

Replace per-doc `_create_translation_prompt(...)` path with shared `context_prompt_text`.
Keep additional custom instructions appended once during context pass.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -k "uses_context_prompt"`
Expected: PASS.

**Step 5: Commit**

```bash
git add ai/epub_translate_roundtrip.py tests/unit/test_epub_translate_roundtrip.py
git commit -m "feat: reuse context pass prompt for full epub translation"
```

### Task 6: Checkpoint Compatibility with Context Signature / Prompt Hash

**Files:**
- Modify: `ai/epub_translate_roundtrip.py`
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Write the failing test**

```python
def test_checkpoint_invalidated_when_context_signature_changes() -> None:
    # run once, mutate context inputs, rerun
    assert resumed_docs == 0
```

Add test for `--force-context-rebuild` always invalidating context cache.

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -k "context_signature_changes or force_context_rebuild"`
Expected: FAIL.

**Step 3: Write minimal implementation**

Add fields to checkpoint state:

```python
"context_signature": context_signature,
"prompt_hash": prompt_hash,
"state_version": 2
```

Maintain backward reader compatibility for version 1.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py -k "context_signature_changes or force_context_rebuild"`
Expected: PASS.

**Step 5: Commit**

```bash
git add ai/epub_translate_roundtrip.py tests/unit/test_epub_translate_roundtrip.py
git commit -m "feat: add context-aware checkpoint compatibility for epub roundtrip"
```

### Task 7: Integration + Docs + Full Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md` (if prompt flow contract documented there)
- Test: `tests/unit/test_epub_translate_roundtrip.py`

**Step 1: Add/adjust integration-like assertions**

In existing unit/integration harness, assert:
- `epub_orchestration/01-analysis.md` exists
- `epub_orchestration/02-prompt.md` exists
- `epub_orchestration/context_manifest.json` exists

**Step 2: Run focused tests**

Run: `uv run pytest -q tests/unit/test_epub_translate_roundtrip.py`
Expected: PASS.

**Step 3: Run full quality gates**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
bash -n translatebook.sh
```

Expected: all pass.

**Step 4: Commit docs and final changes**

```bash
git add README.md docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md ai/epub_context_pass.py ai/epub_translate_roundtrip.py 09_epub_translate_roundtrip.py translatebook.sh tests/unit/test_epub_translate_roundtrip.py
git commit -m "feat: add epub-first context pass and shared prompt roundtrip flow"
```

