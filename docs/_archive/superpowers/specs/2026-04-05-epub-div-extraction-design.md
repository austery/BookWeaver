# Conservative EPUB `div` Extraction Design

## Problem

`book_translated4.epub` exposed a structural blind spot in the EPUB workflow: `extract_translatable_segments()` only recognizes `p`, `li`, `blockquote`, and `dd` blocks. This works for many EPUBs, but fails on weak-semantic books where prose is wrapped in generic `div` containers (for example `div.calibre16` from Calibre/Kindle conversion chains).

The result is not a model-quality failure. Large parts of the book never enter translation at all, so no bilingual output is injected for those sections.

## Goals

1. Translate prose-bearing `div` leaf blocks in EPUB XHTML.
2. Keep the current conservative behavior for headings, TOC/nav documents, tables, metadata-like content, and layout wrappers.
3. Avoid duplicate extraction when an outer container wraps an inner translatable block.
4. Prevent resume/checkpoint corruption after segment ordering changes.

## Non-Goals

1. Do not add class-name allowlists such as `calibre16`.
2. Do not change prompt content, model routing, batching, or sanity-probe thresholds.
3. Do not change current TOC/table source-only behavior.
4. Do not attempt a full semantic reconstruction of arbitrary EPUB layouts.

## Chosen Approach

Use a **structure-based leaf-block heuristic** instead of a pure tag whitelist.

### Candidate blocks

The extractor will treat these tags as candidate block nodes:

- `p`
- `li`
- `blockquote`
- `dd`
- `div`

### `div` qualification rules

A `div` is translatable only when **all** of the following are true:

1. It has non-empty visible text after normal whitespace normalization.
2. It has no descendant translatable block node (`leaf-only` rule).
3. It is not inside skipped ancestors such as `script` or `style`.
4. It is not in a TOC/contents document.
5. It is not heading-like.
6. It is not a structural container for table/list/image/navigation content.

### Conservative heading-like `div` rule

To avoid regressing heading handling when generic `div` support is added, a `div` is considered heading-like if either:

1. Existing class hints match (`head`, `title`, `subhead`), or
2. The node is a **short inline-only emphasized wrapper**:
   - normalized visible text length is `<= 120`
   - it has no descendant candidate block nodes
   - all text is carried by inline descendants
   - it contains emphasis signals such as `b`, `strong`, or class names containing `bold`

This intentionally keeps lines such as `CHAPTER 1`, `PREFACE BY ...`, and short bold section titles source-only.

### Structural-container exclusions

`div` nodes that act as wrappers around richer structure must stay source-only. At minimum, exclude `div` nodes with descendants in:

- `table`, `thead`, `tbody`, `tr`, `th`, `td`, `caption`
- `ul`, `ol`, `dl`
- `img`, `svg`
- `nav`

The extractor should continue to prefer the innermost actual prose block rather than an outer layout container.

## Patching Behavior

Patching remains conservative and unchanged in spirit:

1. `li` translations stay nested inside the source `li`.
2. Other qualified blocks, including qualified `div` blocks, receive a sibling `<p class="bw-translation">...</p>` immediately after the source block.
3. TOC documents still suppress rendered translations.

No class-specific output behavior will be introduced.

## Checkpoint / Resume Safety

This fix changes EPUB segment extraction order and count. Existing checkpoint IDs use `doc_path::index`, so blindly reusing older checkpoints can attach old translations to the wrong source segments after the new extractor ships.

To prevent silent corruption:

1. Add a new checkpoint metadata field, `segmenter_signature`.
2. For EPUB runs, set it to an explicit constant describing the extraction contract, e.g. `epub-leaf-block-v2`.
3. Treat a missing or mismatched `segmenter_signature` as a resume incompatibility and start fresh unless a future, explicit migration path is implemented.

This is safer than relying on the current input/prompt metadata alone.

## Test Strategy

Implementation must be TDD-first and add at least these tests:

1. `extract_translatable_segments()` extracts prose from a `div`-only XHTML sample.
2. Short bold heading-style `div` nodes are not extracted.
3. Outer container `div` nodes wrapping inner `p`/`blockquote` content are not double-counted.
4. `patch_xhtml_alternating()` injects one sibling `bw-translation` block after a qualified prose `div`.
5. Existing table/TOC/list behavior remains unchanged.
6. Resume logic rejects checkpoints when `segmenter_signature` is missing or mismatched.

Tests should use minimal XHTML fixtures that model the real failure pattern from *The Great Depression* without depending on the full book file.

## Risks and Trade-offs

### Main risk

Over-broad `div` support can accidentally translate layout wrappers or short title lines.

### Mitigation

The design deliberately biases toward **false negatives over false positives**:

- leaf-only extraction
- explicit heading-like `div` exclusion
- structural-container exclusion
- checkpoint invalidation for safety
- regression tests around current EPUB behavior

### Accepted trade-off

Some unusual prose wrapped in heavily styled short `div` blocks may still remain source-only. That is acceptable for this phase because the priority is to close the large prose gap without destabilizing the EPUB pipeline.

## Rollout Notes

1. Implement in a dedicated git worktree to isolate the risky extractor change from the main workspace.
2. Keep the change set focused on EPUB extraction/patching and checkpoint compatibility.
3. Do not bundle unrelated glossary, prompt, or rendering work into the same change.
