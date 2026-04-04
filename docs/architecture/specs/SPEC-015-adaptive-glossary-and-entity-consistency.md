---
specId: SPEC-015
title: Adaptive Glossary and Entity Consistency Strategy
status: 📝 草案 (Draft)
priority: P1 - Core Feature
creationDate: 2026-04-04
lastUpdateDate: 2026-04-04
owner: Lei Peng (AI-Assisted)
relatedSpecs:
  - SPEC-010
  - SPEC-011
  - SPEC-012
  - SPEC-013
tags:
  - glossary
  - entity-consistency
  - epub
  - adaptive-strategy
  - terminology-extraction
  - translation-quality
---

# SPEC-015: Adaptive Glossary and Entity Consistency Strategy

## 1. Goal

Enable adaptive pre-translation terminology handling so both technical books and fiction-like worldbuilding books maintain stable term/name consistency without requiring full-book expensive extraction.

## 2. Background

SPEC-010 introduced a strong index-driven terminology extraction pipeline, which works well when EPUBs expose standard index structures. Real library scans now show high structural variance:

- many books have no usable index at all;
- some books include index semantics under non-standard names (`ix01.xhtml`) or markup (`epub:type="index"`, `data-type="index"`);
- fiction/long-form narrative can still require consistency for names, organizations, places, and world-specific terms even without a classic index.

Current behavior can degrade into “TOC-only” extraction in these cases, which is better than nothing but not enough for high-consistency translation goals.

This SPEC defines an adaptive strategy that avoids all-or-nothing extraction and introduces a low-cost fallback for entity consistency.

## 3. Design Decision

**Chosen approach**: Introduce a signal-scored adaptive pipeline with three modes (`heavy`, `light`, `minimal`) and make `light` fallback the default when index signals are weak.

**Rationale**: A score-driven decision model is more robust than hard-coding by book genre and controls cost while preserving translation consistency.

| Alternative | Pros | Cons | Decision |
|-------------|------|------|----------|
| Keep index-only extraction (current + small patches) | Small code change | Still brittle for non-standard EPUBs and fiction consistency | ❌ Rejected |
| Force full-book NER extraction for all books | Highest recall | High token/time cost; poor ROI on many books | ❌ Rejected |
| **Adaptive heavy/light/minimal with signal scoring** | Best cost/quality balance; handles diverse structures | Adds orchestration complexity | ✅ Chosen |

## 4. Implementation Phases

### Phase 1: Index signal scorer and mode resolver — Target: TBD

- [ ] Add `IndexSignalScorer` to inspect manifest names, spine-tail headers, and XHTML index markup signals.
- [ ] Expand detection to include:
  - [ ] filename patterns beyond `index|idx` (e.g., `ix\d+`)
  - [ ] markup signals (`epub:type="index"`, `data-type="index"`)
  - [ ] heading hints (`Index`, `Glossary`, `Searchable Terms`)
  - [ ] line-shape patterns (term + locator/page markers)
- [ ] Add mode resolver:
  - [ ] `heavy` when index score >= threshold
  - [ ] `light` when score is medium/low but extraction signals exist
  - [ ] `minimal` only when no useful signals and extraction fallback disabled

**Acceptance**: For a representative corpus, mode resolution is deterministic and logged with reasons.

### Phase 2: Light mode entity consistency extractor — Target: TBD

- [ ] Implement lightweight entity extractor from sampled content windows (e.g., front chapters + sampled tail sections), not full-book scan.
- [ ] Extract and rank:
  - [ ] person names
  - [ ] organizations
  - [ ] place/world terms
  - [ ] high-frequency domain terms
- [ ] Build compact glossary payload with confidence and source attribution.
- [ ] Keep strict max terms budget to control prompt bloat.

**Acceptance**: `light` mode emits a non-empty consistency glossary for books lacking classic index but containing recurring named entities.

### Phase 3: User micro-dictionary overlay — Target: TBD

- [ ] Add optional user-supplied override dictionary input (`--glossary-overrides` or equivalent).
- [ ] Define precedence: user overrides > auto glossary > model default behavior.
- [ ] Support minimal schema: `term`, `translation`, optional `negative_constraint`.
- [ ] Integrate with existing prompt block assembly.

**Acceptance**: User can pin 5–20 critical names/terms without running heavy extraction.

### Phase 4: Runtime integration and observability — Target: TBD

- [ ] Emit structured logs for:
  - [ ] resolved mode (`heavy|light|minimal`)
  - [ ] trigger signals and score
  - [ ] glossary source (`index`, `light-entity`, `user-override`)
  - [ ] final term counts by priority
- [ ] Expose mode controls in CLI/config (with safe defaults).
- [ ] Ensure compatibility with existing `--extract-glossary` and `--glossary-min-priority`.

**Acceptance**: Operators can understand why a book took a given glossary path from logs alone.

### Phase 5: Validation corpus and quality gates — Target: TBD

- [ ] Add regression corpus classes:
  - [ ] technical books with standard index
  - [ ] technical books with non-standard index naming/markup
  - [ ] fiction/worldbuilding books with no explicit index
  - [ ] narrative books with low terminology density
- [ ] Add unit tests for scorer/extractor/mode resolver.
- [ ] Add integration tests for mode-specific prompt injection.
- [ ] Define quality metrics:
  - [ ] name consistency rate
  - [ ] key-term consistency rate
  - [ ] extraction cost overhead (time/tokens)

**Acceptance**: Adaptive strategy improves consistency metrics over baseline without unacceptable runtime cost increase.

## 5. Acceptance Criteria

- [ ] Non-standard index books (e.g., `ix01.xhtml` + index markup) are correctly routed to `heavy` or at least yield non-empty index-derived glossary.
- [ ] Books without explicit index still receive `light` consistency extraction by default (unless explicitly disabled).
- [ ] User override dictionary is supported and deterministically takes precedence.
- [ ] Runtime logs clearly explain glossary path and score rationale.
- [ ] Existing SPEC-010 flows remain backward compatible for known-good index books.
- [ ] Tests cover scorer logic, mode routing, and prompt payload composition for all three modes.

## 6. Status History

| Date | Status | Note |
|------|--------|------|
| 2026-04-04 | 📝 草案 (Draft) | Initial adaptive strategy draft from cross-book scan and glossary miss analysis |

## 7. Related

- **Code**: `ai/glossary_extractor.py`
- **Code**: `ai/glossary_injector.py`
- **Code**: `ai/cli.py`
- **Config**: `config/config.json.example`
- **Specs**: [SPEC-010](./SPEC-010-terminology-extraction-translation-constraints.md)
- **Specs**: [SPEC-011](./SPEC-011-model-selection-and-config-abstraction.md)
- **Specs**: [SPEC-012](./SPEC-012-core-translation-engine-hexagonal.md)
- **Specs**: [SPEC-013](./SPEC-013-pipeline-completion-shell-replacement.md)

