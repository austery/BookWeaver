# ADR-0007: Preset-driven execution with separated model and effort axes

Status: Accepted (2026-11-11). Approved by the owner in conversation.

## Context

BookWeaver originally exposed free-form `--model`, `--provider`, and reasoning effort flags. As subscription CLIs and metered APIs multiplied, combinations created confusion, invalid configurations, silent upstream fallbacks, and untracked resume states.

## Decision

Model and reasoning effort are decoupled as two explicit, orthogonal axes. The CLI and local API reject arbitrary combinations; users select only named, pre-certified presets (e.g. `agy-flash-low`, `claude-sonnet-5-5-low`, `codex-5-3-low`). Free-form combinations and silent substitutions fail loudly.

## Reason

- "Free-form model and provider flags create false model identity, accidental fallback, and unverified runtime behavior." (SPEC-025 §3.8)
- "Model selection and reasoning effort are separate user axes; presets establish tested, certified pairings." (AGENTS.md)
- "Presets give the local API and CLI a shared, predictable catalog (`bookweaver presets`)." (SPEC-026)

## Alternatives

- Retaining free-form `--model` and `--effort` strings: rejected to eliminate silent fallbacks and uncertified combinations.
- Dynamic auto-detection of optimal model/effort: rejected per ADR-0002 (no silent substitution).

## Consequences

Adding or upgrading a model requires an explicit entry in `ai/model_profiles.py` and verification before it becomes selectable. Users cannot run arbitrary unlisted model names.
