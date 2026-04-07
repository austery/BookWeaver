# Simplify Glossary Ladder to Two Tiers

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Tier 2 (local-refinement heuristics) entirely; auto mode falls back directly from Tier 1 (index) to Tier 3 (deep-scan whole-book AI extraction). Raise default max-terms from 20 to 50. Relax Tier 3 prompt to include important names/places.

**Architecture:** Two-tier ladder: Tier 1 = scored index/glossary doc detection (fast, cheap). If no strong index signals found, fall through to Tier 3 = whole-book LLM scan (sends full text, model selects terms). Tier 2 (local heuristics) is removed from code and marked as future architecture in its module.

**Tech Stack:** Python, pytest, EPUB/zipfile. No new dependencies.

---

## Files Changed

| File | Action | Responsibility |
|------|--------|----------------|
| `ai/glossary_extractor.py` | Modify | Remove Tier 2 block; auto-fallback goes to deep-scan; raise default max_terms to 50; relax Tier 3 prompt |
| `ai/core/local_glossary_candidates.py` | Modify docstring only | Mark as "future architecture, not used in current pipeline" |
| `00_extract_glossary.py` | Modify | Raise default `--max-terms` from 20 to 50 |
| `tests/unit/test_glossary_extractor.py` | Modify | Replace Tier 2 fallback tests with Tier 3 fallback tests; update regression matrix |
| `docs/architecture/specs/SPEC-015-adaptive-glossary-and-entity-consistency.md` | Modify | Update to reflect 2-tier design |

---

## Task 1: Relax Tier 3 prompt and raise default max_terms

**Files:**
- Modify: `ai/glossary_extractor.py:189-222` (prompt) and `ai/glossary_extractor.py:502` (default)

- [ ] **Step 1: Write failing test for name-inclusive prompt**

In `tests/unit/test_glossary_extractor.py`, add to the bottom:

```python
def test_deep_scan_prompt_allows_names_and_places():
    """Tier 3 prompt must NOT exclude names/places — biographies need them."""
    from ai.glossary_extractor import _DEEP_SCAN_PROMPT_TEMPLATE
    assert "不要人名" not in _DEEP_SCAN_PROMPT_TEMPLATE
    assert "不要地名" not in _DEEP_SCAN_PROMPT_TEMPLATE
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/spec-015-glossary-ladder
uv run pytest tests/unit/test_glossary_extractor.py::test_deep_scan_prompt_allows_names_and_places -v
```

Expected: FAIL (current prompt contains "不要人名、地名、机构名")

- [ ] **Step 3: Update `_DEEP_SCAN_PROMPT_TEMPLATE` in `ai/glossary_extractor.py`**

Replace the `提取要求` block (lines ~202-208):

```python
_DEEP_SCAN_PROMPT_TEMPLATE = """\
你是技术书籍翻译专家。以下是一本书的完整正文内容（整本书 / whole-book）。

<BOOK_CONTEXT>
标题: {book_title}
总文档数: {doc_count}
总字符数: {char_count}
</BOOK_CONTEXT>

<WHOLE_BOOK>
{full_text}
</WHOLE_BOOK>

任务：通读整本书，提取**所有容易翻译错误或需要统一翻译**的关键词汇（最多{max_terms}条）。

提取要求：
1. 优先选择专业术语、科学概念、作者原创新词
2. 包含重要人名、机构名、地名（如对翻译一致性有影响）
3. 优先识别"易混淆"的术语对（拼写相似但含义不同）
4. 标注作者原创的新概念（本书首次提出的术语）
5. 按重要性分级：critical（核心概念）, high（高频术语）, medium（次要）

严格输出以下JSON格式，不要包含任何其他文字：
{{
  "critical_terminology": [
    {{
      "term": "原文术语",
      "suggested_translation": "建议的中文翻译",
      "negative_constraint": "NOT 容易混淆的错误翻译（可选）",
      "reason": "为什么这个术语容易翻译错误或需要统一",
      "priority": "critical|high|medium"
    }}
  ]
}}
"""
```

Also update the function default: `def extract_glossary_from_epub(..., max_terms: int = 50, ...)`

- [ ] **Step 4: Run test to confirm it passes**

```bash
uv run pytest tests/unit/test_glossary_extractor.py::test_deep_scan_prompt_allows_names_and_places -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/glossary_extractor.py tests/unit/test_glossary_extractor.py
git commit -m "fix: relax Tier 3 prompt to include names/places, raise default max_terms to 50"
```

---

## Task 2: Remove Tier 2 from `extract_glossary_from_epub`, auto-fallback to Tier 3

**Files:**
- Modify: `ai/glossary_extractor.py` — remove Tier 2 block (lines ~568-631), auto mode falls to deep-scan

- [ ] **Step 1: Write the failing test for Tier 3 auto-fallback**

In `tests/unit/test_glossary_extractor.py`, find the two tests that currently assert `"local-refinement"`:
- `test_extract_glossary_auto_falls_back_to_local_refinement_when_no_index_signals` (line ~537)
- `test_extract_glossary_auto_ignores_toc_only_books_and_uses_local_refinement` (line ~579)

Replace both with updated versions asserting `"deep-scan"`:

```python
def test_extract_glossary_auto_falls_back_to_deep_scan_when_no_index_signals(
    tmp_path: Path,
) -> None:
    """Tier 1 auto mode must fall back to Tier 3 deep-scan when no index signals exist."""
    epub_path = _make_test_epub(
        tmp_path,
        files={
            "OEBPS/content.opf": _make_opf(spine_items=["chapter.xhtml"]),
            "OEBPS/chapter.xhtml": _make_xhtml(
                "<p>Some body content without any index structure.</p>"
            ),
        },
    )
    calls: list[str] = []

    def capture_fn(prompt: str) -> str:
        calls.append(prompt)
        return _VALID_GLOSSARY_JSON

    report = extract_glossary_from_epub(
        epub_path=epub_path,
        output_path=tmp_path / "out.json",
        translate_fn=capture_fn,
    )
    assert report["tier"] == "deep-scan", "No-index auto mode must fall back to Tier 3"
    assert len(calls) == 1
    # Tier 3 prompt should contain the chapter body text
    assert "body content" in calls[0]


def test_extract_glossary_auto_toc_only_falls_back_to_deep_scan(
    tmp_path: Path,
) -> None:
    """Auto mode TOC-only books must fall back to Tier 3 deep-scan, not Tier 2."""
    epub_path = _make_test_epub(
        tmp_path,
        files={
            "OEBPS/content.opf": _make_opf(spine_items=["toc.xhtml", "chapter.xhtml"]),
            "OEBPS/toc.xhtml": _make_xhtml("<nav><ol><li>Chapter 1</li></ol></nav>"),
            "OEBPS/chapter.xhtml": _make_xhtml("<p>Body text here.</p>"),
        },
    )

    def simple_fn(prompt: str) -> str:
        return _VALID_GLOSSARY_JSON

    report = extract_glossary_from_epub(
        epub_path=epub_path,
        output_path=tmp_path / "out.json",
        translate_fn=simple_fn,
    )
    assert report["tier"] == "deep-scan", "TOC-only must fall back to Tier 3"
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest tests/unit/test_glossary_extractor.py::test_extract_glossary_auto_falls_back_to_deep_scan_when_no_index_signals tests/unit/test_glossary_extractor.py::test_extract_glossary_auto_toc_only_falls_back_to_deep_scan -v
```

Expected: FAIL (function not found or wrong tier)

- [ ] **Step 3: Remove Tier 2 block from `extract_glossary_from_epub`**

In `ai/glossary_extractor.py`, replace lines ~568-631 (the entire "Tier 2" block):

**Remove** the block that starts with:
```python
        # Tier 2 fallback: Local refinement when no strong index signals
        print(
            "[glossary] No strong index signals, falling back to Tier 2 (local refinement)",
```

**Replace with** a direct fall-through to Tier 3:
```python
        # Tier 1 failed: fall through to Tier 3 whole-book deep-scan
        print(
            "[glossary] No strong index signals, falling back to Tier 3 (deep-scan)",
            flush=True,
        )
        mode = "deep-scan"

    # Tier 3: Deep-scan (whole-book extraction) — triggered explicitly or as auto fallback
```

Then remove the guard `if mode == "auto":` block entirely. The Tier 3 block (`if mode == "deep-scan":`) will handle both cases.

Also **remove** the now-unused import from the top of the file:
```python
# Remove this import:
from ai.core.local_glossary_candidates import (
    TextBlock,
    build_local_glossary_candidates,
)
```

Also remove `_LOCAL_REFINEMENT_PROMPT_TEMPLATE` (lines ~152-188 in the current file — the entire template string).

- [ ] **Step 4: Run the new tests**

```bash
uv run pytest tests/unit/test_glossary_extractor.py::test_extract_glossary_auto_falls_back_to_deep_scan_when_no_index_signals tests/unit/test_glossary_extractor.py::test_extract_glossary_auto_toc_only_falls_back_to_deep_scan -v
```

Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest tests/unit/test_glossary_extractor.py -q
```

Fix any remaining failures from old `local-refinement` assertions:
- Line ~823: `assert report2["tier"] in ("index", "local-refinement")` → change to `in ("index", "deep-scan")`
- Line ~835: `assert report3["tier"] == "local-refinement"` → change to `== "deep-scan"`
- Line ~847: `assert report4["tier"] == "local-refinement"` → change to `== "deep-scan"`

- [ ] **Step 6: Run full suite (all tests)**

```bash
uv run pytest -q
```

Expected: all pass (same count as before minus removed Tier 2 tests + new Tier 3 fallback tests)

- [ ] **Step 7: Commit**

```bash
git add ai/glossary_extractor.py tests/unit/test_glossary_extractor.py
git commit -m "refactor: remove Tier 2 local-refinement, auto mode falls back to Tier 3 deep-scan"
```

---

## Task 3: Mark `local_glossary_candidates.py` as future architecture

**Files:**
- Modify: `ai/core/local_glossary_candidates.py` (docstring only)

- [ ] **Step 1: Update module docstring**

Replace the current module docstring (lines 1-9) with:

```python
"""Local glossary candidate extraction (FUTURE ARCHITECTURE — not used in current pipeline).

This module provides zero-dependency heuristics for extracting high-value terminology
from EPUB spine text using title-case entity detection and multiword phrase matching.

Status: Retained for future integration with NLP-based Tier 2 (e.g., spaCy NER,
TF-IDF). The current pipeline uses Tier 1 (index detection) → Tier 3 (whole-book
AI scan) without this module.

If you want to re-introduce a lightweight local pre-filter layer between Tier 1 and
Tier 3, this is the starting point. Pair with scikit-learn TfidfVectorizer or spaCy
en_core_web_sm for improved recall on scientific/fiction terminology.
"""
```

- [ ] **Step 2: Run tests to confirm nothing broke**

```bash
uv run pytest -q
```

Expected: same pass count

- [ ] **Step 3: Commit**

```bash
git add ai/core/local_glossary_candidates.py
git commit -m "docs: mark local_glossary_candidates as future architecture (not used in pipeline)"
```

---

## Task 4: Raise default `--max-terms` to 50 in `00_extract_glossary.py`

**Files:**
- Modify: `00_extract_glossary.py:39`

- [ ] **Step 1: Update the argparse default**

```python
    parser.add_argument(
        "--max-terms",
        type=int,
        default=50,
        help="Maximum number of terms to extract (default: 50)",
    )
```

- [ ] **Step 2: Verify syntax**

```bash
uv run python -m py_compile 00_extract_glossary.py && echo ok
```

- [ ] **Step 3: Commit**

```bash
git add 00_extract_glossary.py
git commit -m "fix: raise default --max-terms to 50 in 00_extract_glossary.py"
```

---

## Task 5: Update SPEC-015 to reflect 2-tier design

**Files:**
- Modify: `docs/architecture/specs/SPEC-015-adaptive-glossary-and-entity-consistency.md`

- [ ] **Step 1: Update the tier descriptions in the spec**

Find the section describing the three-tier ladder and replace with:

```markdown
## Extraction Ladder (Two-Tier)

### Tier 1 — Index/TOC Detection (default, fast)
- Scores each EPUB spine document with `IndexSignalScorer`
- Threshold: 35+ points → classified as index/glossary doc
- Content threshold: index text must be > 100 chars to qualify
- Sends index text + TOC to LLM → structured JSON glossary
- Triggered by: `--glossary-mode auto` (default)

### Tier 3 — Whole-Book Deep Scan (fallback and explicit)
- Triggered when: Tier 1 finds no qualifying index, OR `--glossary-mode deep-scan`
- Sends full EPUB spine text (~500K chars for a typical book) to LLM
- Model reads entire book and selects the most translation-critical terms
- Includes: technical terms, scientific concepts, author-coined words, AND
  important names/places where consistent translation matters
- Default max terms: 50

### Tier 2 (Future Architecture)
- Local heuristic pre-filter using Python stdlib regex (zero AI cost)
- Code retained in `ai/core/local_glossary_candidates.py` but NOT active
- Suitable for future NLP upgrade path (spaCy NER, TF-IDF)
- Limitation: 90%+ false positives on sentence-initial capitalized words;
  misses lowercase scientific terms (mRNA, pseudouridine, in vitro)
```

- [ ] **Step 2: Commit**

```bash
git add docs/architecture/specs/SPEC-015-adaptive-glossary-and-entity-consistency.md
git commit -m "docs: update SPEC-015 to reflect 2-tier design (Tier 1 → Tier 3)"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

Expected: all pass, no lint errors.

- [ ] **Smoke test: standalone extraction with new default**

```bash
uv run python 00_extract_glossary.py --help | grep max-terms
# Should show: default: 50
```

- [ ] **Smoke test: Tier 3 via 00_extract_glossary.py**

```bash
uv run python 00_extract_glossary.py \
  '/Users/leipeng/Documents/Calibre_Books/Katalin Kariko/Breaking Through_ My Life in Science (5)/Breaking Through_ My Life in Science - Katalin Kariko.epub' \
  --output /tmp/kariko_test.json \
  --max-terms 50 \
  --glossary-mode deep-scan \
  --model pro
cat /tmp/kariko_test.json | python3 -m json.tool | grep '"term"'
```

- [ ] **Final commit tag**

```bash
git log --oneline -6
```
