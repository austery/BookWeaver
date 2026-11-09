---
specId: SPEC-011
title: Model Selection and Config Abstraction (Model Alias & Provider Mapping)
status: 📝 草案 (Draft)
priority: P1 - Core Feature
creationDate: 2026-03-26
lastUpdateDate: 2026-03-26
owner: leipeng (AI-Assisted)
relatedSpecs:
  - SPEC-002
  - SPEC-006
tags:
  - model-selection
  - configuration
  - gemini
  - provider
  - refactor
---

# SPEC-011: Model Selection and Config Abstraction

## 1. Goal

Provide a clear, testable, and configuration-driven object layer that resolves user-requested model identifiers (CLI flags, aliases like `pro`) into concrete provider model names (e.g., `gemini-2.5-pro`), eliminating scattered hard-coded alias mappings and ensuring the configured value in JSON takes precedence.

## 2. Background

Current behavior observed:
- Running `translatebook.sh --model pro` resolved to `gemini-3-pro-preview` at runtime.
- Hard-coded alias mapping exists in `ai/epub_translate_roundtrip.py` (e.g. `_MODEL_ALIASES = {"pro": "gemini-3-pro-preview"}`) and is referenced across docs/tests (CLAUDE.md, tests/*).
- A configuration file (e.g., `config/config.json`) contains model preferences (e.g., `default_model`: `gemini-2.5-pro`) but the codebase still uses in-code aliases in some paths.

Pain points:
- Config does not fully control runtime model resolution.
- Multiple places duplicate alias logic → maintenance and correctness risk.
- Tests and docs assume different canonical model names.

## 3. Design Decision

Chosen approach: Introduce a single ModelResolver object-layer responsible for resolving a requested model identifier into a final provider model name. The resolver will:

- Accept sources in precedence order: CLI override -> per-run config (temp/overrides) -> repository config (`config/config.json`) -> environment variable -> built-in alias fallbacks -> provider probe/fallback chain.
- Load alias mapping from config (allowing repository-level overrides) and fall back to a built-in default alias list only when config doesn't define them.
- Expose a typed enum (Python enum.Enum) for known logical model roles (e.g., ModelRole.PRO, ModelRole.FLASH, ModelRole.LITE) to document intent and reduce magic strings.
- Be unit-testable and injectable (dependency injection) into high-level translation entrypoints (03_translate_md.py, 09_epub_translate_roundtrip.py, ai/gemini_provider.py).

Rationale:
- Centralization reduces duplicated logic and ensures configuration takes precedence.
- Enum provides static documentation and reduces Name/Meaning coupling.
- Injection makes testing and future provider swaps (e.g., different model family) simpler.

Alternatives considered:

| Alternative | Pros | Cons | Decision |
|-------------|------|------|---------|
| Keep current per-file alias maps | Minimal code changes | Continued drift, hard-to-audit mappings | ❌ Rejected |
| Use environment-only resolution | Easy for CI | Not user-friendly, ignores config files | ❌ Rejected |
| Central resolver + enum (Chosen) | Clear precedence, testable, configurable | Moderate refactor work | ✅ Chosen |

## 4. Implementation Phases

### Phase 1: Discovery & API Design — Target: TBD
- [ ] Inventory all occurrences of model alias resolution (grep for known alias strings: `pro`, `flash`, `lite`, `gemini-3-pro-preview` etc.) — done (partial list: ai/epub_translate_roundtrip.py, CLAUDE.md, tests).
- [ ] Design `ModelResolver` API and `ModelRole` enum. Document in-code docstring and README snippet.

Deliverable: API doc + small example usage snippet.

### Phase 2: Implementation — Target: TBD
- [ ] Implement `ai/model_resolver.py` with:
  - `ModelRole(Enum)` definitions for logical roles.
  - `ModelResolver` class with method `resolve(requested: str|ModelRole) -> str`.
  - Config loader that reads `config/config.json` (and `config/*.json`) for `model_aliases` and `default_model` keys.
  - Precedence rules implementation and unit tests.
- [ ] Replace ad-hoc alias lookups in `ai/epub_translate_roundtrip.py`, `03_translate_md.py`, and provider initialization (`ai/gemini_provider.py`) to use `ModelResolver`.

### Phase 3: Tests & Docs — Target: TBD
- [ ] Add unit tests for `ModelResolver` covering:
  - CLI override wins
  - Repo config alias overrides built-in
  - Unknown alias triggers probe/fallback behavior
  - Enum usage resolves as expected
- [ ] Add integration test that runs a dry-run of translatebook with `--model pro` and asserts final provider model equals config value.
- [ ] Update CLAUDE.md and README examples to point at new behavior.

### Phase 4: Rollout & Cleanup — Target: TBD
- [ ] Deprecate any remaining in-file `_MODEL_ALIASES` definitions with TODO comments and remove after migration.
- [ ] Update docs/plans referencing the old alias to reflect the canonical model names.

## 5. Acceptance Criteria

- [ ] `ModelResolver` implemented and covered by unit tests (pytest).
- [ ] Running `translatebook.sh --model pro` resolves to the model defined in `config/config.json` when present (and to CLI override when provided).
- [ ] No code path contains a hard-coded authoritative alias mapping that overrides config; remaining hard-coded fallbacks are documented and covered by a test.
- [ ] Integration test exercising EPUB workflow with `--model pro` passes in CI.
- [ ] Documentation updated (CLAUDE.md noted and README examples) and SPEC-011 marked `📝 草案 (Draft)` → `🟡 待实施` when ready.

## 6. Status History

| Date | Status | Note |
|------|--------|------|
| 2026-03-26 | 📝 草案 (Draft) | Initial draft created after user report of alias/preview mismatch |

## 7. Related

- Code: `ai/epub_translate_roundtrip.py`, `ai/gemini_provider.py`, `03_translate_md.py`
- Config: `config/config.json` (repository-level model_aliases & default_model)
- Docs: `CLAUDE.md`, `docs/architecture/specs/SPEC-002-prompt-model-stability.md`
- Tests: `tests/unit/test_gemini_provider.py`, `tests/unit/test_translate_step3_refactor.py`




