# EPUB Block Anchor Redesign Design

## Context

Current EPUB translate roundtrip uses fine-grained `text/tail` slots as translation anchors.
This causes two readability issues in real books:

- One visual paragraph often receives multiple translation insertions.
- Translation can be injected inside inline tags such as `<a>`, making output awkward.

Multi-book sampling in `tmp/` confirms this is a general issue, not a single-book edge case.

## Goal

Redesign anchor granularity from inline slots to block-level nodes so bilingual output remains readable while preserving EPUB structure integrity.

## Non-Goals

- Do not change prompt design in this task.
- Do not remove existing batch translation + binary split retry behavior.
- Do not change package integrity validation scope.

## Approaches Considered

### A) Block-level anchor redesign (Recommended)

Extract only block nodes (`p/li/blockquote/td/th/dd`) from body, translate per block, and patch translation as a sibling block.

Pros:
- One block -> one translation block mapping.
- Prevents inline tag pollution (`a/span/em/...`).
- Better reading rhythm for technical books.

Cons:
- Requires new extraction/patch schema and tests.

### B) Block-level with inline placeholders

Protect selected inline tags (`a/code/...`) using placeholders before translation, then restore.

Pros:
- Better inline fidelity.

Cons:
- Higher complexity and placeholder robustness risk.

### C) Minimal patch

Keep current extraction; only prevent insertion into `<a>`.

Pros:
- Smallest code change.

Cons:
- Does not solve multi-translation-per-paragraph fragmentation.

## Chosen Design

Use **Approach A** now; keep B as a future enhancement if needed.

### Data Model

Introduce block segment metadata:

- `block_xpath`: stable path to locate the source block
- `source_text`: normalized readable text for translation
- `tag_name`: original block tag (for patch placement policy)

### Extraction Rules

From each non-TOC spine XHTML:

1. Find `<body>`.
2. Traverse descendants and collect translatable block tags:
   - include: `p`, `li`, `blockquote`, `td`, `th`, `dd`
   - exclude headings (`h1-h6`) and non-content containers
3. Build one segment per block (not per inline text slot).
4. Preserve order for deterministic patching.

### Translation Rules

- Keep current per-document batch strategy with `%%` separator.
- Keep binary split retry on mismatch/timeout.
- Segment count contract remains strict.

### Patching Rules

For each translated block segment:

1. Locate source block by `block_xpath`.
2. Append exactly one translation sibling block after source block:
   - default: `<p class="bw-translation">...</p>`
   - if parent disallows `<p>` (e.g. list/table contexts), use compatible block tag fallback.
3. Never inject translation inside inline tags (`a/span/em/strong/code/...`).
4. Keep TOC docs source-only and heading source-only behavior.

### Compatibility and Integrity

- Keep OPF/manifest/spine/link integrity checks unchanged.
- Continue allowing pre-existing source broken fragments while blocking newly introduced ones.

## Validation Plan

### Unit Tests

- Extractor returns block-level segments in source order.
- Patcher inserts one translation block per source block.
- No `bw-translation` appears inside `<a>`.
- Existing anchor IDs and href attributes remain unchanged.

### Multi-book Sampling (5 books in tmp)

For each sampled book (3 body chapters):

- `anchor-embedded-translation` count should be zero.
- `paragraphs-with-multi-translations` ratio should drop significantly vs current.
- Manual readability check on 2-3 representative passages.

### Regression

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest -q`
- `bash -n translatebook.sh`
- `uv run python -m py_compile 09_epub_translate_roundtrip.py ai/epub_translate_roundtrip.py ai/epub_package.py`

## Rollout

1. Feature-flag internally in code path first (for safe comparison).
2. Replace old slot extractor/patcher once tests and sampling pass.
3. Update README and SPEC-006 behavior notes.
