---
specId: SPEC-007
title: Unified YAML Configuration Governance
status: 📝 草案 (Draft)
priority: P1 - Core Feature
creationDate: 2026-03-18
lastUpdateDate: 2026-03-18
owner: Lei Peng (AI-Assisted)
relatedSpecs:
  - SPEC-002
  - SPEC-006
tags:
  - configuration
  - yaml
  - runtime-governance
  - model-catalog
  - environment-override
---

# SPEC-007: Unified YAML Configuration Governance

## 1. Goal

> Establish a single, layered YAML configuration system so BookWeaver runtime behavior stays centralized, auditable, and easy to update as Gemini models evolve quickly.

## 2. Background

BookWeaver currently mixes configuration sources:

- `config/config.json.example` for model aliases, probe candidates, and defaults
- CLI flags for runtime overrides
- hardcoded constants in some new modules (for example, translate-roundtrip aliases)

This creates drift risk, especially when Gemini model names rotate every quarter. The owner also uses centralized config patterns in another project (`default.yml + custom-environment-variables.yml`) and wants equivalent governance here.

Security boundary remains unchanged: secrets (API keys/tokens) must stay in environment variables, not static config files.

## 3. Design Decision

**Chosen approach**: Adopt a layered YAML runtime config model with explicit ENV mapping and keep JSON only where external tooling contracts require it.

**Rationale**: This keeps human-editable configuration centralized while preserving machine-readable JSON only for tool-specific metadata that is not application runtime policy.

| Alternative | Pros | Cons | Decision |
|-------------|------|------|----------|
| A) Layered YAML (`default.yml` + env-specific/local override + env mapping) | Centralized governance, readable diffs, easy quarterly model refresh | Migration work required | ✅ Chosen |
| B) Single YAML only | Simplest file model | Weak environment separation and override ergonomics | ❌ Rejected |
| C) Keep JSON as primary runtime config | Lowest immediate migration cost | Harder long-term governance, higher drift risk | ❌ Rejected |

## 4. Configuration Architecture

### 4.1 Files and Precedence

Runtime config precedence (highest to lowest):

1. Environment variables (via mapping file)
2. Local override YAML (untracked, machine/user-specific)
3. Environment YAML (optional)
4. `config/default.yml` (tracked baseline)

### 4.2 Secrets Policy

- Secrets are never stored in tracked YAML.
- Keys/tokens remain ENV-only.
- YAML stores non-secret runtime policies (model aliases, batching, prompts, format defaults, integrity behavior).

### 4.3 JSON Boundary

JSON is allowed only for external contract surfaces (for example, third-party skill metadata schemas), not for BookWeaver runtime configuration governance.

## 5. Implementation Phases

### Phase 1: Runtime Config Loader Foundation — Target: TBD

- [ ] Add YAML loader with layered merge and typed schema validation.
- [ ] Add `custom-environment-variables.yml` style mapping for ENV overrides.
- [ ] Introduce `config/default.yml` with parity to current runtime JSON keys.

**Acceptance**: Existing commands run with no behavior change when YAML mirrors current JSON settings.

### Phase 2: Feature Migration and Alias Unification — Target: TBD

- [ ] Migrate roundtrip model alias resolution to unified YAML config.
- [ ] Migrate roundtrip batch controls (`batch_max_segments`, `batch_timeout_seconds`) to YAML-backed defaults.
- [ ] Remove hardcoded alias/batch constants from translation modules.

**Acceptance**: Both legacy and roundtrip paths read model/batch policies from one YAML governance layer.

### Phase 3: Deprecation and Ops Workflow — Target: TBD

- [ ] Mark JSON runtime config path as deprecated and remove after transition window.
- [ ] Add quarterly model catalog refresh workflow (probe + issue/PR reminder).
- [ ] Update contributor docs and release notes.

**Acceptance**: Runtime config is YAML-first; model refresh is a repeatable scheduled operation.

## 6. Acceptance Criteria

- [ ] BookWeaver runtime policy can be fully configured without editing source code.
- [ ] Model aliases and probe candidates are defined in YAML only.
- [ ] Roundtrip and legacy translation flows use the same config source for model mapping.
- [ ] Secrets remain ENV-only and absent from tracked config files.
- [ ] Quarterly model refresh process is documented and automatable.

## 7. Risks and Mitigations

- **Risk**: Migration breaks compatibility for existing users.
  - **Mitigation**: Dual-read transition period (YAML preferred, JSON fallback) before hard cutover.
- **Risk**: YAML schema drift causes runtime surprises.
  - **Mitigation**: Strict typed validation on startup with fail-fast errors.
- **Risk**: Frequent model rotation causes stale aliases.
  - **Mitigation**: Scheduled refresh task and explicit ownership.

## 8. Status History

| Date | Status | Note |
|------|--------|------|
| 2026-03-18 | 📝 草案 (Draft) | Initial spec for centralized YAML governance and model-refresh strategy |

## 9. Related

- **Current runtime config**: `config/config.json.example`
- **Translation entrypoints**: `03_translate_md.py`, `ai/epub_translate_roundtrip.py`
- **Specs**: [SPEC-002](./SPEC-002-prompt-model-stability.md), [SPEC-006](./SPEC-006-epub-translate-roundtrip.md)
