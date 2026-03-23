---
specId: SPEC-009
title: EPUB Inline Link Preservation and Index Page Handling
status: 🔵 待办 (Backlog)
priority: P2 - Enhancement
creationDate: 2026-03-23
lastUpdateDate: 2026-03-23
owner: User (AI-Assisted)
relatedSpecs:
  - SPEC-006
  - SPEC-008
tags:
  - epub
  - translation
  - links
  - index
  - footnote
  - inline-html
---

# SPEC-009: EPUB Inline Link Preservation and Index Page Handling

## 1. Goal

Preserve `<a href>` hyperlinks inside translated XHTML segments so that footnote
references and index page-number jumps remain functional after bilingual injection.

## 2. Background

The current EPUB translation pipeline (`ai/epub_package.py`) uses two complementary
mechanisms that lose inline link structure:

1. **Text extraction** — `extract_translatable_segments` calls `ET.Element.itertext()`
   to collect plain text. Any `<a href="...">N</a>` span is flattened to the bare
   number `N`.

2. **Translation injection** — `patch_xhtml_alternating` inserts the translated string
   as `translated_block.text = translation`. This is raw text, not markup, so there
   is no way to carry link elements back into the DOM.

Two concrete symptoms were observed on a production EPUB:

### Symptom A — Footnote reference numbers go dead

Body paragraphs that contain inline endnote references like

```html
<p>…the authors announced.<a epub:type="noteref" href="#fn5"><sup>5</sup></a></p>
```

are extracted as `"…the authors announced.5"`. After translation the model returns
`"…作者们宣布。5"` and this plain string is injected; the `<a>` element is gone and
clicking "5" does nothing.

### Symptom B — Index page-number links go dead

Index entries are structured as:

```html
<li>AARP, <a href="#page_82">82</a></li>
```

Extracted text is `"AARP, 82"`, injected translation is plain `"AARP, 82"` — the
jump-to-page link is silently dropped.

Additionally, `_is_toc_document` only checks for `"toc"` / `"contents"` in the
filename. Files named `index.xhtml`, `idx.xhtml`, or similar are not recognised as
navigation-only documents, so they receive full bilingual injection even though:

- Index entries are reference artifacts, not narrative prose.
- Translating proper nouns, book titles, and legal act names inside index entries
  produces incorrect output (e.g. translating `The Affluent Society` or
  `Administrative Procedure Act (1946)`).
- The page-number links are the index's primary value; losing them degrades usability.

## 3. Design Decision

This SPEC tracks two independent sub-problems with different complexity and urgency.

### Sub-problem 1 — Index page skip (quick win)

**Chosen approach**: Extend `_TOC_DOC_HINTS` to include common index filename hints
(`"index"`, `"idx"`). Index documents will behave like TOC documents: segments are
extracted (so the model receives them) but translation is **not** rendered back into
the DOM — the source xhtml is passed through unchanged.

| Alternative | Pros | Cons | Decision |
|---|---|---|---|
| Extend `_TOC_DOC_HINTS` | 2-line change, consistent with existing TOC skip | Heuristic; misses custom names | ✅ Chosen |
| `epub:type="index"` attribute check | Semantically correct | Requires parsing `<body epub:type>` or manifest metadata | ❌ Too complex for now |
| Translate but strip injected translations | Preserves translated text if needed later | Complicates code with no immediate benefit | ❌ Rejected |

**Open question**: Should we still translate index headings (e.g. "A", "B", "C"
section dividers)? Deferred — source-only is safer default.

### Sub-problem 2 — Inline link preservation (complex)

**Chosen approach (tentative)**: Placeholder substitution before translation, restore
after.

Algorithm:
1. Before calling the model, scan each segment's source `ET.Element` for inline `<a>`
   children and replace them with numbered placeholders: `[[LINK:0]]`, `[[LINK:1]]`, …
2. Pass the placeholder-substituted text to the model.
3. After receiving the translation, locate each `[[LINK:N]]` marker and re-insert the
   original `ET.Element` at that position.
4. If the model drops or corrupts a placeholder, fall back to plain-text injection (no
   worse than current behaviour).

| Alternative | Pros | Cons | Decision |
|---|---|---|---|
| Placeholder substitution | Lossless round-trip; model sees clean text | Requires structural extraction + re-insertion; adds complexity | ✅ Tentative |
| Post-hoc numeric heuristic | Simple | Fragile; only works for digit-only link text | ❌ Rejected |
| Instruct model to preserve `<a>` tags | Zero code change | Models frequently reformat or drop tags; unreliable | ❌ Rejected |
| Source-only for all inline-link segments | Safe; zero breakage | Loses translation for mixed prose+footnote paragraphs | ❌ Too aggressive |

**Note**: Sub-problem 2 is significantly more complex than Sub-problem 1 and touches
the core extraction/injection contract. It should be designed and implemented
separately after Sub-problem 1 is shipped and validated.

## 4. Implementation Phases

### Phase 1: Index page skip — `_TOC_DOC_HINTS` extension

**Target**: TBD (quick win, estimated small effort)

- [ ] Add `"index"` and `"idx"` to `_TOC_DOC_HINTS` in `ai/epub_package.py`
- [ ] Add unit test: `_is_toc_document("OEBPS/index.xhtml")` → `True`
- [ ] Add unit test: `_is_toc_document("text/idx.xhtml")` → `True`
- [ ] Verify existing TOC tests still pass
- [ ] Manual smoke test: translate a real index-containing EPUB; confirm index xhtml
  is unchanged in output

**Acceptance**: Index xhtml in translated output is byte-for-byte identical to source.

### Phase 2: Inline link placeholder round-trip

**Target**: TBD (medium effort, requires design review before implementation)

- [ ] Write design sub-spec or ADR for placeholder substitution algorithm
- [ ] Extend `TranslatableSegment` to carry `inline_links: list[InlineLink]` metadata
- [ ] Implement `_extract_inline_links(node)` — returns placeholder-substituted text
  and link registry
- [ ] Implement `_restore_inline_links(translation, registry)` — re-inserts `<a>`
  elements at placeholder positions
- [ ] Handle fallback: if placeholders are missing from model output, log warning and
  inject plain text
- [ ] Add unit tests for extraction, restoration, and fallback paths
- [ ] Regression: existing tests must pass unchanged

**Acceptance**:
- A round-trip of a body paragraph containing `<a epub:type="noteref">` produces an
  injected translation element that contains the same `<a>` structure (same `href`,
  same text content).
- If the model omits a placeholder, the pipeline emits a warning but does not crash.

## 5. Acceptance Criteria

- [ ] Index xhtml is not modified during translation (source-only pass-through)
- [ ] Footnote `<a epub:type="noteref">` elements survive bilingual injection with
  `href` and text content intact
- [ ] Page-number `<a href="#page_N">` elements in index (if index is ever translated)
  survive injection
- [ ] No regressions in existing 130-test suite
- [ ] CLAUDE.md updated to document new skip-list hints and placeholder behaviour

## 6. Status History

| Date | Status | Note |
|---|---|---|
| 2026-03-23 | 🔵 待办 (Backlog) | Initial draft; no solution finalised for Phase 2 |

## 7. Related

- **Code**: `ai/epub_package.py` — `_TOC_DOC_HINTS`, `_BLOCK_TAGS`,
  `extract_translatable_segments`, `patch_xhtml_alternating`
- **Code**: `ai/epub_translate_roundtrip.py` — `translate_segments_with_batch_retry`
- **Specs**: [SPEC-006](./SPEC-006-epub-translate-roundtrip.md) — translate roundtrip
  quality contract
- **Specs**: [SPEC-008](./SPEC-008-epub-block-anchor-redesign.md) — block anchor
  redesign
