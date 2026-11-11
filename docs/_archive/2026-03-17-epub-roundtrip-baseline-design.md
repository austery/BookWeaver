# EPUB Roundtrip Baseline Design

## Context

Current `markdown -> rendered HTML -> ebook-convert` flow can produce EPUBs that differ from source books in navigation behavior, cover handling, and structural fidelity.

For baseline quality validation, we need a strict roundtrip path that preserves original EPUB structure and behavior.

## Goals

- Baseline mode must perform **zero text mutation**.
- Preserve cover semantics (`meta name="cover"`, guide/nav/titlepage references).
- Preserve clickable TOC/navigation behavior.
- Preserve manifest/spine ordering and resource paths.
- Produce validation and diff evidence against the original EPUB.

## Non-Goals

- No translation in baseline mode.
- No visual redesign or typography normalization in baseline mode.
- No replacement of original CSS/layout assets.

## Approaches Considered

### A. Repack-first (Recommended)

Unzip original EPUB, parse package metadata, keep content/resources untouched in baseline mode, then repack with strict integrity checks.

Pros:
- Highest structural fidelity.
- Best chance to preserve cover + links + reader behavior.

Cons:
- Requires EPUB-aware validation tooling and integrity checks.

### B. Hybrid

Keep only some source files (cover/nav), while re-rendering body from intermediate HTML/Markdown.

Pros:
- Lower implementation effort than full preservation.

Cons:
- Still high risk of anchor drift and TOC breakage.

### C. Full reflow conversion

Continue current `ebook-convert`-centric reflow path.

Pros:
- Simple flow.

Cons:
- Inherently lossy for strict roundtrip requirements.

## Design

### 1) Architecture

Introduce **Roundtrip Baseline Mode** (separate from translation flow):

`EPUB unzip -> OPF/NAV model -> integrity checks -> repack -> epubcheck + diff report`

Translation flow remains separate but will reuse package-model components.

### 2) Components

1. `epub_unpacker`: unzip and index files.
2. `opf_nav_model`: parse OPF manifest/spine/guide + nav/toc references.
3. `resource_classifier`: classify immutable files (baseline) vs editable content (translation mode).
4. `xhtml_patcher`: text-node-only mutation for translation mode (not used in baseline).
5. `epub_repacker`: deterministic repack and output.
6. `link_integrity_checker`: validate internal href/id graph.
7. `asset_integrity_checker`: validate image/css/font references and existence.

### 3) Policy Switches

- **Baseline policy**: zero text mutation, zero structural rewrite.
- **Translation policy**:
  - mutate only body text nodes in selected content XHTML.
  - keep nav/toc files untouched by default.
  - keep original fonts and append CJK fallback stack only.

### 4) Data Flow

#### Baseline

1. Load source EPUB package model.
2. Validate core pointers:
   - cover item + titlepage reference
   - nav/toc resources
   - spine order and linearity
3. Repack without mutation.
4. Run checks + comparison report.

#### Translation

1. Build package model.
2. Select translatable spine items.
3. Patch text nodes only, preserving ids/classes/anchors.
4. Repack and validate links/resources.

## Validation & Acceptance

### Baseline Acceptance

- `epubcheck` passes.
- OPF cover metadata preserved.
- guide/nav references preserved.
- spine sequence unchanged.
- image/css/font resource counts and relative paths preserved.
- TOC link targets resolvable (no broken fragment links).

### Comparison Report

Generate machine-readable report:
- file inventory diff
- OPF critical fields diff
- link graph stats (total, valid, broken)
- cover/titlepage pointer checks

## Open-Source Practices Incorporated

- Preserve package document semantics (EPUB package/nav model).
- Avoid unnecessary reflow conversion for strict-fidelity use cases.
- Validate after packaging (`epubcheck` as quality gate).

## Risks

- Reader-specific behavior variance even with valid EPUB.
- Some source EPUBs contain non-standard quirks requiring compatibility exceptions.

## Next Step

Create implementation plan for:
1. baseline mode CLI entry and workflow,
2. package/link integrity validators,
3. comparison report generation,
4. translation-mode integration boundary.
