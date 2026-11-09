---
specId: SPEC-014
title: EPUB Segment Scaffolding Protocol Recovery
status: 🟡 待实施 (Ready for Implementation)
priority: P1 - Core Feature
creationDate: 2026-04-03
lastUpdateDate: 2026-04-03
owner: Lei Peng (AI-Assisted)
relatedSpecs:
  - SPEC-010
  - SPEC-012
  - SPEC-013
tags:
  - epub
  - prompt-protocol
  - translation-quality
  - adapter-layer
  - tdd
  - regression-fix
---

# SPEC-014: EPUB Segment Scaffolding Protocol Recovery

## 1. Goal

Restore strict segment-boundary scaffolding for EPUB multi-segment translation payloads so prose quality regressions are mitigated without rolling back the hexagonal architecture.

## 2. Background

After SPEC-012 refactor, EPUB translation moved to unified `ai.cli` path and simplified prompt/protocol behavior. A/B testing showed:

- prompt recovery improves tone/persona moderately;
- weak boundary contract in multi-segment payloads still risks segment bleed/format drift in some runs;
- quality/stability issues are multi-factor, so this SPEC isolates one variable first.

This SPEC intentionally does **not** change batch planning strategy in core engine. It restores protocol scaffolding at adapter boundary only.

## 3. Design Decision

**Chosen approach**: Implement EPUB-only, default-on tagged segment scaffolding at adapter protocol layer (`ai/adapters/providers/_delimiter.py`), with strict parse/validation and TDD-first rollout.

**Rationale**: Boundary protocol belongs to transport/serialization concerns, not core batching domain. This keeps architecture clean and blast radius small.

| Alternative | Pros | Cons | Decision |
|-------------|------|------|----------|
| Adapter-layer protocol replacement (EPUB-only) | Minimal invasive, keeps hex boundaries, fast rollback | Adds EPUB-specific protocol branch | ✅ Chosen |
| CLI-layer payload wrapping | Quick patch | Pollutes composition root with transport details | ❌ Rejected |
| Full strategy-object protocol framework | Clean long-term extensibility | Too large for this regression fix | ❌ Rejected |

## 4. Implementation Phases

### Phase 1: Protocol implementation (EPUB-only) — Target: TBD

- [ ] Add EPUB multi-segment serializer with `<segment id="n">...</segment>` framing.
- [ ] Add EPUB parser for tagged response extraction and ID mapping.
- [ ] Keep single-segment path unchanged.
- [ ] Keep non-EPUB paths on current protocol.

**Acceptance**: EPUB multi-segment request/response is fully round-trippable via tagged protocol with strict count/id validation.

### Phase 2: Defensive parsing hardening — Target: TBD

- [ ] Strip optional fenced code wrappers (e.g., ```xml ... ```) before tag parsing.
- [ ] Parse with regex/global capture (`re.DOTALL`) instead of naive split.
- [ ] Validate unique, contiguous IDs from 1..N.
- [ ] Return precise `TranslationError` reasons for malformed outputs.

**Acceptance**: Malformed or decorated outputs are deterministically handled; valid outputs parse reliably.

### Phase 3: Empty segment policy — Target: TBD

- [ ] Define normalization rule for empty/whitespace-only segments in payload.
- [ ] Ensure parser/validator does not enter pathological split-retry loops for empty segment omission.
- [ ] Add explicit tests for empty segment scenarios.

**Acceptance**: Empty segment handling is deterministic and does not create infinite retry-split behavior.

### Phase 4: Prompt addendum reinforcement — Target: TBD

- [ ] Strengthen adapter addendum language (hard contract tone).
- [ ] Require preserving segment wrappers and exact one-to-one mapping.
- [ ] Explicitly forbid merge/split/add/drop behavior.

**Acceptance**: Contract text is explicit and aligns with parser expectations.

## 5. Acceptance Criteria

- [ ] EPUB multi-segment batches use tagged scaffolding protocol by default.
- [ ] Parser enforces strict ID/count validation and rejects malformed mappings.
- [ ] Fenced-wrapper and multiline-tag outputs are parseable when structurally valid.
- [ ] Empty-segment scenarios are handled without retry dead loops.
- [ ] Existing core batch algorithm remains unchanged.
- [ ] `tests/unit/test_adapter_providers.py` and `tests/unit/test_cli.py` cover new behavior and pass.

## 6. Status History

| Date | Status | Note |
|------|--------|------|
| 2026-04-03 | 🟡 待实施 (Ready for Implementation) | Initial spec drafted from A/B regression analysis and review feedback |

## 7. Related

- **Code**: `ai/adapters/providers/_delimiter.py`
- **Code**: `ai/adapters/providers/gemini_cli_adapter.py`
- **Code**: `ai/cli.py`
- **Tests**: `tests/unit/test_adapter_providers.py`
- **Tests**: `tests/unit/test_cli.py`
- **Specs**: [SPEC-010](./SPEC-010-terminology-extraction-translation-constraints.md)
- **Specs**: [SPEC-012](./SPEC-012-core-translation-engine-hexagonal.md)
- **Specs**: [SPEC-013](./SPEC-013-pipeline-completion-shell-replacement.md)
