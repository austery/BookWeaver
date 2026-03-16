---
specId: SPEC-002
title: Prompt Externalization and Model Stability Layer
status: 🟡 待实施 (Ready for Implementation)
priority: P1 - Core Feature
creationDate: 2026-03-16
lastUpdateDate: 2026-03-16
owner: Lei Peng (AI-Assisted)
relatedSpecs:
  - SPEC-001
tags:
  - prompt-template
  - model-selection
  - gemini-cli
  - fallback
  - probe-cache
  - runtime-stability
---

# SPEC-002: Prompt Externalization and Model Stability Layer

## 1. Goal

> Ensure BookWeaver remains runnable when Gemini model names evolve by moving prompts to external profiles and using config-driven model alias + startup probing + fallback selection.

## 2. Background

Current pain points in runtime maintenance:

- Prompt content is coupled to implementation logic in `03_translate_md.py`.
- Model compatibility is vulnerable to naming changes in Gemini CLI.
- Operational stability depends on code edits instead of config updates.

User priority for this SPEC: **stability first** (model changes should be handled without code rewrites).

Related references:

- Existing baseline pipeline in `SPEC-001`.
- Public prompt profile patterns from `immersive-translate/prompts` (e.g. `ebook.yml`).
- Similar prompt-file workflow seen in `baoyu-translate` (`02-prompt.md` style).

## 3. Design Decision

**Chosen approach**: Config-driven prompt profiles + startup model probing + ordered fallback chain.

**Rationale**: Balances robustness and complexity; avoids brittle hardcoded allow-lists while keeping behavior auditable.

| Alternative | Pros | Cons | Decision |
|-------------|------|------|----------|
| A. Config + startup probe + fallback chain | Stable against model renames; transparent runtime logs; low manual intervention | Slight startup overhead; cache management needed | ✅ Chosen |
| B. Pure static config (no probe) | Simplest implementation | Breaks silently when configured model becomes unavailable | ❌ Rejected |
| C. Fully dynamic self-learning selector | Potentially optimal quality/cost over time | High complexity, lower explainability, harder to debug | ❌ Rejected |

## 4. Implementation Phases

### Phase 1: Prompt Externalization — Target: TBD

- [ ] Add `config/prompts/default_prompt.txt`
- [ ] Add `config/prompts/ebook_prompt.txt`
- [ ] Extend `config/config.json.example` with `prompt_profile` and `prompt_templates`
- [ ] Update `03_translate_md.py` to load prompt template by profile
- [ ] Keep `-p/--prompt` as appended custom instructions

**Acceptance**: Prompt text is no longer hardcoded in step logic; profile switch works via config only.

### Phase 2: Model Alias & Startup Probe — Target: TBD

- [ ] Add `model_aliases` and `fallback_chain` in config
- [ ] Add model probe utility with cache (timestamp + gemini version)
- [ ] Resolve `--model` through alias map before runtime selection
- [ ] Probe requested/candidate models and select first available
- [ ] On full failure, emit actionable error with attempted models

**Acceptance**: Unknown/new model names can be used via config; no fixed model whitelist blocks execution.

### Phase 3: Integration, DX, and Docs — Target: TBD

- [ ] Surface selected model/profile in logs and dry-run output
- [ ] Update `README.md` and `CLAUDE.md` with profile/model behavior
- [ ] Align script help text (`translatebook.sh`) with real runtime behavior
- [ ] Add regression checks for full pipeline dry-run output

**Acceptance**: User can diagnose model/profile behavior without reading source code.

## 5. Acceptance Criteria

- [ ] Prompt profiles are external files and selected by config (`prompt_profile`).
- [ ] Runtime supports alias-based model selection (`pro/flash/lite`) and full model names.
- [ ] Startup probe + fallback chain determines final model without hardcoded allow-list.
- [ ] Config change alone can adapt to model-name updates.
- [ ] `uv run pytest -q` passes with new prompt/model tests.
- [ ] Dry-run clearly shows selected profile, selected model, and fallback path (if used).

## 6. Status History

| Date | Status | Note |
|------|--------|------|
| 2026-03-16 | 📝 草案 (Draft) | Initial design captured from brainstorming |
| 2026-03-16 | 🟡 待实施 (Ready for Implementation) | Design validated; implementation plan prepared |

## 7. Related

- **Code**: `03_translate_md.py`, `ai/gemini_provider.py`, `translatebook.sh`, `config/config.json.example`
- **Specs**: [SPEC-001](./SPEC-001-multi-tier-gemini-translation.md)
- **Design Doc**: `docs/plans/2026-03-16-prompt-model-stability-design.md`
- **Implementation Plan**: `docs/plans/2026-03-16-prompt-model-stability-implementation.md`
