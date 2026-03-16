# Prompt & Model Stability Design (BookWeaver)

Date: 2026-03-16

Status: Approved

## 1. Goal

Stabilize translation runtime against fast-changing model names while making prompt strategy externally configurable.

Primary priority: **stability first** (no code change required when model names evolve).

## 2. Background

Current pain points:

- Prompt is coupled to `03_translate_md.py` implementation details.
- Model handling has historically relied on hardcoded assumptions.
- Runtime behavior should remain reliable when Gemini model names change.

Reference findings:

- Public prompt templates exist in `immersive-translate/prompts` (e.g. `plugins/ebook.yml`, `plugins/fiction.yml`) with a profile-based structure.
- Sample projects (`translate-book`, `baoyu-translate`) use prompt files/templates rather than embedding long prompts in core runtime logic.

## 3. Chosen Approach

Selected approach: **Config-driven + startup probing**.

Why:

- Keeps behavior explicit and auditable.
- Supports new model names via config updates.
- Avoids hard failure on stale allow-lists.

## 4. Design

### 4.1 Config & Prompt Profiles

Add/extend config keys:

- `prompt_profile` (default: `default`)
- `prompt_templates` (`profile -> template path`)
- `model_aliases` (`pro/flash/lite -> concrete model name`)
- `model_probe` (enabled, candidates, cache TTL)
- `fallback_chain` (ordered fallback models/aliases)

Prompt files:

- `config/prompts/default_prompt.txt`
- `config/prompts/ebook_prompt.txt` (initially minimal viable eBook-focused profile)

### 4.2 Runtime Model Resolution

Runtime order:

1. Parse user `--model` (if provided)
2. Resolve alias from `model_aliases`
3. Run lightweight availability probe for requested/candidate models
4. If unavailable, walk `fallback_chain`
5. If all fail, surface explicit error with probe results

Key rule:

- No strict static whitelist in provider path; use probe-based runtime truth.

### 4.3 Prompt Rendering Flow

Data flow:

`config -> prompt_profile -> template file -> placeholder rendering -> Gemini call`

Placeholders:

- `{TARGET_LANGUAGE}`
- `{CUSTOM_INSTRUCTIONS_BLOCK}`

Migration principle:

- Keep `default` behavior backward-compatible.
- Allow explicit profile switch to `ebook`.
- Missing template should fail loudly with clear diagnostics.

## 5. Error Handling

- Probe failure must include model name + stderr snippet.
- Missing config/template must return actionable file path hints.
- Fallback path must log attempted models in order.

## 6. Testing Strategy (TDD)

Add/extend tests for:

- Prompt template loading and placeholder replacement
- `--model` acceptance for non-hardcoded model names
- alias resolution behavior
- probe cache hit / miss / expiry
- fallback-chain selection behavior

Regression checks:

- `uv run pytest -q`
- dry-run output includes selected model and active prompt profile
- 3-chunk sample comparison (`default` vs `ebook`)

## 7. Acceptance Criteria

1. New model names are usable via config update (no code edit required).
2. Prompt strategy is file-driven and profile-switchable.
3. Runtime failures are explainable (probe logs + fallback logs).
4. Existing default flow remains stable.

## 8. Out of Scope (This Iteration)

- Automatic quality scoring and adaptive online model learning.
- Complex multi-profile orchestration beyond `default + ebook`.
