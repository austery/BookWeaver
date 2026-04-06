---
specId: SPEC-015
title: Adaptive Glossary Extraction Ladder and Entity Consistency
status: 📝 草案 (Draft)
priority: P1 - Core Feature
creationDate: 2026-04-04
lastUpdateDate: 2026-04-05
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
  - zero-dependency
  - deep-scan
  - cost-control
  - terminology-extraction
---

# SPEC-015: Adaptive Glossary Extraction Ladder and Entity Consistency

## 1. Goal

Enable stable translation of technical terms and fiction entities by choosing the cheapest reliable glossary extraction path first and requiring explicit user opt-in for any whole-book high-token scan.

## 2. Background

SPEC-010 introduced an EPUB glossary extraction flow centered on Index + TOC analysis. That path works well for books with standard index structures, and the current implementation already includes several useful heuristics:

- filename hints such as `index` / `idx`;
- tail-spine content checks for Kindle-style alphabetical index markers;
- line-pattern heuristics for non-standard index pages;
- mixed-language separation that prefers English source terms for glossary generation.

Real-world EPUB scans still show high structural variance:

- many books have no usable index at all;
- some books expose index/glossary semantics under non-standard names (`ix01.xhtml`) or markup (`epub:type="index"`, `data-type="index"`);
- many fiction or worldbuilding books care more about entity consistency (people, places, factions, invented terms) than classic back-of-book terminology;
- the project should not add heavy local NLP dependencies such as `spaCy` or `scikit-learn` just to improve glossary recall;
- the CLI must never trigger a whole-book high-token extraction call automatically, because that creates surprise API cost.

Current behavior can degrade into “TOC-only” extraction or no glossary at all. That is better than nothing, but it is not enough for the consistency goals of BookWeaver when translating technical books, fiction, or mixed narrative/reference works.

This SPEC replaces the previous heavy/light/minimal draft with a clearer three-tier glossary ladder:

- Tier 1: automatic `index-heavy` extraction when structural signals are strong;
- Tier 2: automatic `light-local` extraction using zero-dependency Python heuristics plus LLM refinement;
- Tier 3: explicit `deep-ai` whole-book extraction, available only when the user requests it.

Scope for this SPEC remains EPUB auto-extraction. Existing manual glossary injection via `--glossary <path>` stays supported and continues to use the current glossary JSON schema (`critical_terminology` with `term`, `suggested_translation`, optional `negative_constraint`, and `priority`).

## 3. Design Decision

**Chosen approach**: Introduce a three-tier glossary extraction ladder: automatic Tier 1 `index-heavy`, automatic Tier 2 `light-local`, and explicit Tier 3 `deep-ai` triggered only by `--glossary-mode deep-scan`.

**Rationale**: This approach improves recall for books without a clean index, avoids dependency bloat, preserves the existing glossary schema/injection path, and guarantees that expensive whole-book extraction never happens implicitly.

| Alternative | Pros | Cons | Decision |
|-------------|------|------|----------|
| Keep index-only extraction (current + small patches) | Small code change | Still brittle for non-standard EPUBs and fiction/entity consistency | ❌ Rejected |
| Add local NLP libraries (`spaCy`, `scikit-learn`) for entity/keyword extraction | Better local NLP accuracy | Dependency bloat, packaging complexity, heavier install/runtime footprint | ❌ Rejected |
| Automatically deep-scan full books when heuristics think the book is “small enough” | Highest recall with less operator involvement | Surprising token cost; violates CLI cost-control expectations | ❌ Rejected |
| **Three-tier ladder: Tier 1 index-heavy, Tier 2 zero-dependency local heuristics + LLM refinement, Tier 3 explicit deep scan** | Best balance of recall, runtime cost, and architectural cleanliness | Adds resolver/orchestration logic | ✅ Chosen |

### Tier Summary

| Tier | Trigger | Input Scope | Technique | Cost Profile |
|------|---------|-------------|-----------|--------------|
| Tier 1 `index-heavy` | Automatic when index/glossary signals are strong | Index, TOC, tail spine, glossary-like docs | Signal scoring + current index extraction path | Low |
| Tier 2 `light-local` | Automatic fallback when Tier 1 signals are weak or absent | Full-book plain text extracted locally from EPUB spine docs | Zero-dependency Python heuristics + Gemini refinement of shortlisted candidates | Medium / controlled |
| Tier 3 `deep-ai` | **Explicit CLI request only** via `--glossary-mode deep-scan` | Whole-book plain text | Direct LLM extraction from the full book | Highest / user-approved |

### Resolution Contract

1. If `--glossary <path>` is provided, BookWeaver uses that file directly and ignores auto-extraction flags with a warning.
2. If `--glossary-mode deep-scan` is provided, Tier 3 runs directly.
3. If `--glossary-mode auto` is provided, or the legacy `--extract-glossary` flag is used, BookWeaver runs the automatic ladder:
   - Tier 1 when index/glossary signal score is above threshold.
   - Tier 2 otherwise.
4. Automatic modes may never escalate into Tier 3 on their own.
5. If Tier 2 still yields no usable glossary, BookWeaver continues without an auto glossary and logs the reason.

## 4. Implementation Phases

### Phase 1: CLI contract and glossary policy resolver — Target: TBD

- [ ] Add `--glossary-mode` with at least `auto` and `deep-scan` values.
- [ ] Keep `--extract-glossary` as a backward-compatible alias for `--glossary-mode auto`.
- [ ] Define CLI precedence:
  - [ ] `--glossary <path>` wins over extraction flags
  - [ ] `--glossary-min-priority` continues to apply to all glossary sources
  - [ ] `--glossary-max-terms` continues to cap final emitted terms
- [ ] Add a CLI request-policy resolver that produces one of: `manual`, `auto`, `deep-scan`, or `none`.
- [ ] Keep tier selection inside the EPUB extractor once automatic mode is requested.
- [ ] Emit structured progress logs for resolved request mode, selected tier, explicitness, and skip reasons.

**Acceptance**: A whole-book deep AI scan cannot start unless the user explicitly requests `--glossary-mode deep-scan`, and the chosen glossary path is deterministic from CLI inputs.

### Phase 2: Tier 1 `index-heavy` hardening — Target: TBD

- [ ] Refactor the current index detection logic into a scored `IndexSignalScorer`.
- [ ] Expand signals beyond the current baseline:
  - [ ] filename patterns such as `glossary`, `ix\d+`, and other common short forms
  - [ ] markup signals such as `epub:type="index"`, `epub:type="glossary"`, `data-type="index"`, `data-type="glossary"`
  - [ ] heading hints such as `Index`, `Glossary`, `Searchable Terms`, `Terminology`
  - [ ] line-shape patterns that resemble term + locator/page markers
  - [ ] TOC/back-matter hints that indicate glossary-like documents near the end of the spine
- [ ] Preserve current mixed-language separation and English-first term extraction behavior.
- [ ] Route strong-signal books to the existing index-driven Gemini extraction path.

**Acceptance**: Books with non-standard index naming/markup still resolve to Tier 1 and produce a non-empty index-derived glossary when glossary-like structure is present.

### Phase 3: Tier 2 zero-dependency local prefilter — Target: TBD

- [ ] Build a local plain-text extraction pass over EPUB spine docs using existing package/XHTML text helpers.
- [ ] Normalize whitespace and strip obvious navigation/boilerplate noise before scoring candidates.
- [ ] Implement fiction/entity heuristics using Python standard library only:
  - [ ] regex extraction of title-cased multi-word sequences
  - [ ] regex extraction of repeated single-word proper nouns after stoplist filtering
  - [ ] acronym capture for all-caps entities
  - [ ] source boosts for front matter, dramatis-personae-like lists, appendices, and back matter
- [ ] Implement technical-term heuristics using Python standard library only:
  - [ ] `collections.Counter` over 1-3 word phrases
  - [ ] a hardcoded English stopword list
  - [ ] filters for short tokens, punctuation-only noise, and mostly numeric phrases
  - [ ] ranking boosts for repeated multi-word phrases and heading/TOC/index overlap
- [ ] Merge, deduplicate, and rank local candidates with source attribution.
- [ ] Cap the noisy local shortlist at a fixed upper bound (target: top 300 candidates).

**Acceptance**: Tier 2 runs with zero new third-party NLP dependencies and produces a ranked shortlist that captures recurring entities and terms from books that lack a usable index.

### Phase 4: Tier 2 Gemini refinement and glossary emission — Target: TBD

- [ ] Send the Tier 2 shortlist plus compact book context to Gemini for cleanup and canonicalization.
- [ ] Ask the model to:
  - [ ] remove obvious noise
  - [ ] merge near-duplicate variants
  - [ ] assign `suggested_translation`
  - [ ] emit optional `negative_constraint`
  - [ ] classify `priority` using the existing glossary contract
- [ ] Reuse the current glossary JSON schema (`critical_terminology`) so injection stays backward compatible.
- [ ] Respect `--glossary-max-terms` for the final emitted glossary even if the local shortlist is larger.

**Acceptance**: Tier 2 emits a compact schema-compatible glossary that can be loaded by the current glossary injector without new prompt-side logic.

### Phase 5: Tier 3 explicit `deep-ai` whole-book extraction — Target: TBD

- [ ] Add a dedicated Tier 3 prompt path that performs direct glossary extraction from the whole book.
- [ ] Trigger Tier 3 only when `--glossary-mode deep-scan` is explicitly passed by the user.
- [ ] Log the extraction mode as explicit and include preflight payload diagnostics such as total chars/docs before the request is sent.
- [ ] Reuse the same final glossary JSON schema and output location (`extracted_glossary.json`) as the automatic modes.
- [ ] Never auto-upgrade from Tier 1 or Tier 2 into Tier 3 based on book size, heuristic confidence, or provider availability.

**Acceptance**: Tier 3 gives operators a high-recall glossary path for difficult books, but it is impossible to trigger accidentally.

### Phase 6: Runtime integration, docs, and quality gates — Target: TBD

- [ ] Integrate tier resolution into `ai.cli` and `translatebook.sh`.
- [ ] Keep glossary injection compatible with the current `GlossaryManager` / `GlossaryInjector`.
- [ ] Update user-facing docs to explain `--extract-glossary` vs `--glossary-mode deep-scan`.
- [ ] Add regression corpus classes:
  - [ ] technical books with standard index
  - [ ] technical books with non-standard index naming/markup
  - [ ] fiction/worldbuilding books with no explicit index
  - [ ] narrative books with low terminology density
- [ ] Add unit tests for scorer/resolver/local heuristics.
- [ ] Add integration tests for CLI precedence and tier-specific glossary generation.
- [ ] Track quality metrics:
  - [ ] name consistency rate
  - [ ] key-term consistency rate
  - [ ] extraction overhead (runtime and token cost)

**Acceptance**: The glossary ladder improves consistency over the current baseline while keeping default runtime/API cost bounded and observable.

## 5. Acceptance Criteria

- [ ] `--extract-glossary` remains supported and resolves to the automatic ladder (`Tier 1` or `Tier 2` only).
- [ ] A whole-book LLM glossary extraction cannot run unless the user explicitly requests `--glossary-mode deep-scan`.
- [ ] Tier 2 uses Python standard library heuristics only; it does not add `spaCy`, `scikit-learn`, or similar heavy NLP dependencies.
- [ ] Tier 2 sends at most the configured local shortlist budget (target: top 300 candidates) to Gemini, and final glossary output still honors `--glossary-max-terms`.
- [ ] Manual `--glossary <path>` input remains compatible and bypasses auto extraction deterministically.
- [ ] Non-standard index books (for example `ix01.xhtml` plus glossary/index markup) resolve to Tier 1 and produce index-derived glossary output.
- [ ] Books without explicit index but with recurring names/terms resolve to Tier 2 and produce a non-empty glossary more often than the current baseline.
- [ ] Runtime logs clearly expose resolved tier, explicitness, candidate counts, and skip reasons.
- [ ] Existing glossary JSON schema and prompt injection behavior remain backward compatible for known-good SPEC-010 flows.
- [ ] Tests cover resolver logic, local heuristic ranking, CLI precedence, and prompt payload generation for all three tiers.

## 6. Status History

| Date | Status | Note |
|------|--------|------|
| 2026-04-04 | 📝 草案 (Draft) | Initial adaptive strategy draft from cross-book scan and glossary miss analysis |
| 2026-04-05 | 📝 草案 (Draft) | Reframed as a three-tier ladder with zero-dependency Tier 2 heuristics and explicit opt-in Tier 3 deep scan |

## 7. Related

- **Code**: `ai/glossary_extractor.py`
- **Code**: `ai/core/glossary_resolution.py`
- **Code**: `ai/core/index_signal_scorer.py`
- **Code**: `ai/core/local_glossary_candidates.py`
- **Code**: `ai/glossary_injector.py`
- **Code**: `ai/cli.py`
- **Code**: `translatebook.sh`
- **Config**: `config/schemas/glossary_schema.json`
- **Config**: `config/config.json.example`
- **Specs**: [SPEC-010](./SPEC-010-terminology-extraction-translation-constraints.md)
- **Specs**: [SPEC-011](./SPEC-011-model-selection-and-config-abstraction.md)
- **Specs**: [SPEC-012](./SPEC-012-core-translation-engine-hexagonal.md)
- **Specs**: [SPEC-013](./SPEC-013-pipeline-completion-shell-replacement.md)
