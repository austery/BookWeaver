---
specId: SPEC-008
title: EPUB Block Anchor Redesign for Translate Roundtrip
status: 📝 草案 (Draft)
priority: P1 - Core Feature
creationDate: 2026-03-19
lastUpdateDate: 2026-03-19
owner: Lei Peng (AI-Assisted)
relatedSpecs:
  - SPEC-006
  - SPEC-005
tags:
  - epub
  - translation
  - anchor
  - readability
  - roundtrip
---

# SPEC-008: EPUB Block Anchor Redesign for Translate Roundtrip

## 1. Goal

> Improve bilingual readability by changing translation anchoring from inline text slots to block-level nodes while preserving package integrity guarantees.

## 2. Background

Current translate roundtrip mode (`SPEC-006`) already reduces model call count through per-document batching and recursive split retry.
However, the current extraction/patch strategy is based on fine-grained `text/tail` slots, which frequently creates fragmented bilingual rendering in technical books:

- multiple translations appear within one visual paragraph;
- translations can be inserted inside inline anchors (`<a>...</a>`).

Sampling across five EPUB books in `tmp/` indicates this behavior is general rather than single-book-specific.

## 3. Design Decision

**Chosen approach**: Replace slot-level extraction and patching with block-level extraction and block-level sibling translation insertion.

**Rationale**: Block-level anchoring aligns better with reading flow, eliminates inline anchor pollution, and keeps existing batching/integrity architecture intact.

| Alternative | Pros | Cons | Decision |
|-------------|------|------|----------|
| A. Block-level anchors (p/li/blockquote/td/th/dd) | Readability improves; one source block -> one translation block; robust | Requires extractor/patcher refactor | ✅ Chosen |
| B. Block-level + inline placeholders | Better inline fidelity for complex markup | Higher complexity, placeholder edge cases | ❌ Deferred |
| C. Minimal patch (only avoid `<a>`) | Small implementation effort | Does not solve core paragraph fragmentation | ❌ Rejected |

## 4. Implementation Phases

### Phase 1: Block Segment Data Model and Extraction

- [ ] Replace `TranslatableSegment` payload to support block-location metadata (e.g., XPath/index path).
- [ ] Implement block-level extractor in `ai/epub_package.py`.
- [ ] Keep heading/TOC source-only filtering policy.

**Acceptance**:
- Extracted segments correspond to block nodes only.
- Segment order is deterministic and stable.

### Phase 2: Block-level Patcher

- [ ] Patch translations as sibling block nodes after each source block.
- [ ] Enforce no translation insertion inside inline tags (`a/span/em/strong/code/...`).
- [ ] Keep translation CSS class contract (`bw-translation`) with compatible block rendering.

**Acceptance**:
- Each source block yields at most one translation block.
- No `bw-translation` appears inside `<a>` elements.

### Phase 3: Validation and Multi-book Evaluation

- [ ] Add unit tests for extraction/patching and anchor safety.
- [ ] Compare behavior on multiple books (at least 3 body chapters per book from `tmp/` sample set).
- [ ] Keep full repository verification green.

**Acceptance**:
- `anchor-embedded-translation` count is zero on sampled chapters.
- `paragraphs-with-multi-translations` ratio is significantly reduced versus current behavior.
- Existing integrity checks and pipeline tests still pass.

## 5. Acceptance Criteria

- [ ] Translate roundtrip output avoids inline-anchor translation injection.
- [ ] Bilingual layout for body content is one translation block per source block.
- [ ] TOC and heading source-only policy remains effective.
- [ ] Batch translation retry behavior remains unchanged.
- [ ] Full quality gate passes:
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run pytest -q`
  - `bash -n translatebook.sh`
  - `uv run python -m py_compile 09_epub_translate_roundtrip.py ai/epub_translate_roundtrip.py ai/epub_package.py`

## 6. Status History

| Date | Status | Note |
|------|--------|------|
| 2026-03-19 | 📝 草案 (Draft) | Initial draft for block-anchor redesign |

## 7. Related

- **Code**: `ai/epub_package.py`, `ai/epub_translate_roundtrip.py`
- **Tests**: `tests/unit/test_epub_translate_patcher.py`, `tests/unit/test_epub_translate_roundtrip.py`
- **Design doc**: `docs/plans/2026-03-19-epub-block-anchor-redesign-design.md`
- **Specs**: `SPEC-006`, `SPEC-005`
