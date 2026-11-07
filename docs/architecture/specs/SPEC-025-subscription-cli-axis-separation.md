---
specId: SPEC-025
title: Subscription CLI Runtimes with Separated Model Axes
status: Draft for owner review (2026-11-07)
implementationStatus: Phase 1 implemented and live-verified on agy 1.5.3 (2026-11-07); Phases 2-4 not started
priority: P1 - Runtime Reliability
creationDate: 2026-11-07
lastUpdateDate: 2026-11-07
owner: User (AI-Assisted)
relatedSpecs: [SPEC-020, SPEC-021, SPEC-024]
tags:
  - antigravity
  - codex
  - subscription-cli
  - model-selection
  - effort
  - version-gate
---

# SPEC-025: Subscription CLI Runtimes with Separated Model Axes

## 1. Problem

On 2026-11-07 the default CLI path failed twice in a row after `agy` auto-updated from `1.1.27` to `1.5.3`:

1. The version gate (`CERTIFIED_AGY_VERSIONS`) stopped the run before any model call.
2. After `1.5.3` was certified for flash, `--model pro` failed at discovery: `gemini-3.1-pro-*` is absent from the `1.5.3` roster.

Both failures have one cause. `ai/model_profiles.py` `_CLI_MODELS` folds five axes into one hard-coded string:

| Axis | Example | Who owns it |
|---|---|---|
| Billing / transport | subscription CLI vs metered API | BookWeaver |
| Vendor runtime | Antigravity, Codex | BookWeaver |
| Tier | flash, pro | BookWeaver (user-facing) |
| Effort | low, medium, high | User-facing; validity owned by the runtime |
| Concrete runtime ID | `gemini-3.8-flash-low` | The runtime vendor |

The last row belongs to the vendor, and the vendor changes it without notice. Re-pinning the string after each update treats the symptom.

## 2. Evidence (live, owner machine, 2026-11-07, agy 1.5.3)

| Invocation | Result |
|---|---|
| `--model gemini-3.8-flash-low --effort high` | Hard error: `--model gemini-3.8-flash-low conflicts with --effort=high` |
| `--model gemini-3.8-flash --effort high` | OK; agy resolves `gemini-3.8-flash-high` |
| `--model gemini-4-argon --effort high` | OK; agy resolves `gemini-4-argon-high` |
| `--model gemini-3.1-pro --effort low` | Hard error: `--effort is not supported for model "gemini-3.1-pro"`; no silent substitution |

Consequences:

- agy `1.5.3` treats effort as its own axis and composes `family + effort` itself.
- The current provider passes effort twice (ID suffix and `--effort`). This works only while the two agree.
- agy rejects unknown families and unsupported effort loudly. The strict "no silent substitution" rule holds without a BookWeaver copy of the combination table.

The `1.5.3` roster also lists `claude-opus-5-5-*`, `claude-sonnet-5-5-*` and `gpt-oss-120b-medium` under the same subscription.

## 3. Decisions

### 3.1 Axis separation (owner-confirmed direction)

- The user selects `provider`, `tier` and `effort`. These stay the CLI and config contract.
- The registry maps `(runtime, tier)` to a model **family** plus the owner-enabled efforts. Example: `("antigravity", "flash") -> family "gemini-3.8-flash", efforts {low}`.
- The provider passes effort exactly once, through the runtime's own effort option.
- The runtime still decides whether a `family + effort` pair exists; BookWeaver does not copy the vendor's naming or validity table. The enabled-effort list is a product decision (§3.8), not a copy of vendor rules.
- `ResolvedModel.model_id` keeps the concrete ID (`gemini-3.8-flash-low`) for checkpoint provenance and mixed-model resume warnings. A new `family` field carries the argv value. Existing checkpoints stay compatible.
- Discovery checks that `f"{family}-{effort}"` is in `agy models` and fails loudly otherwise. Runtime-side rejection remains the second guard.

### 3.2 Pro tier (owner decision 2026-11-07)

- `("antigravity", "pro") -> "gemini-4-argon"`.
- It must pass the compatibility probe (§3.3) before release. Gemini 3.1 Pro is retired from the registry.

### 3.3 Version gate: automatic compatibility probe (owner decision 2026-11-07)

The gate guards protocol drift; roster checks already guard model absence.

- Known certified versions run as today.
- An unknown version triggers the existing probe (`scripts/probe_antigravity_version.py` logic, moved into the provider package): three synthetic passages through the production prompt, framing, invocation and `split_response` path. No book content is sent.
- Pass: record `(runtime, version, model_id, protocol, timestamp, result)` in the user-local certification cache `~/.local/state/bookweaver/runtime-certifications.json` (or `$XDG_STATE_HOME/bookweaver/`), then continue. The cache is the probe record; the run audit records `runtime_version` and `row_status`. The probe runs per framing protocol, because glossary extraction uses `delimiter` and translation uses `segment_tags`.
- Fail: stop before any book batch, with the probe diagnosis.
- Cost: three short subscription calls per new `(version, model_id)`. No metered API is ever used for this probe.
- `CERTIFIED_AGY_VERSIONS` becomes a seed list, not the only path.
- SPEC-021's "probe before certifying" rule is kept; the probe becomes automatic instead of manual. Amend SPEC-021 accordingly.

### 3.4 Additional subscription CLIs (owner goals, clarified 2026-11-07)

The owner pays for Antigravity, ChatGPT (Codex) and Claude (Claude Code) subscriptions. Codex and Claude Code are used mainly for programming and their quota is never fully spent; Antigravity quota is mostly unused. Goals:

1. Spend idle subscription quota on book translation instead of metered credit.
2. Translate with GPT models.
3. Cross-check translation quality between vendors (§3.7).

| Candidate | Unique value | Decision |
|---|---|---|
| Codex (`codex exec`) | Separate ChatGPT quota pool; only subscription route to the GPT family | **Add** |
| Claude Code (`claude -p`) | Separate Claude quota pool. The Claude models are also reachable through agy and the Anthropic API, but each route draws on a different pool | **Add** |

Three routes to the same Claude model are acceptable only because each route is a different quota pool. Rules that keep this from becoming the PureSubs state-multiplication pattern:

- The quota pool (= runtime) is an explicit user choice per run. There is no automatic switching between runtimes or pools.
- Provenance records the runtime as well as the model. Today a checkpoint records `provider: cli` and `model_id`; `claude-opus-5-5` through agy and through Claude Code would be indistinguishable. Add `runtime` (`antigravity`, `codex`, `claude-code`) to per-segment provenance.
- Each runtime is one spec on the shared adapter (§3.5), never a separate provider class.

### 3.5 One CLI adapter, many specs

Replace the Antigravity-specific provider with one `SubscriptionCliProvider` plus a typed per-runtime spec. The spec supplies only what differs:

- argv builder (model, effort, prompt transport, timeout);
- read-only lockdown flags;
- roster discovery and version command;
- output extraction (plain stdout, or a final-message file or JSON event);
- error classification (auth, timeout, capacity, artifact-instead-of-text).

Shared and written once: process-group ownership, outer deadline, private prompt-file workspace, segment framing, `split_response`, version gate and probe.

### 3.6 Tool-use lockdown

Both runtimes are agents, not completion endpoints.

- Antigravity: today "do not modify files" is a prompt instruction only. Find and apply a runtime-level restriction; if none exists, record that as an accepted risk. The private temp workspace is the current mitigation.
- Codex: `codex exec --sandbox read-only --ephemeral --skip-git-repo-check`, run inside the private temp workspace.

### 3.7 Quality comparison: human judgment plus AI judge

Goal: decide whether a translated book is good, by two independent means.

- **Human judgment**: the owner reads sampled passages side by side and records a verdict.
- **AI judge**: a model scores translations against the source.

Principles (the detailed design belongs in a separate evaluation spec):

- Evaluation is a separate step over finished checkpoints, not a mode inside a translation run. The translation path stays unchanged.
- The judge is a role, not a new runtime. It uses the same subscription CLI adapter with a different prompt and output schema.
- The judge vendor differs from the translator vendor, to reduce self-preference bias. Example: a Gemini translation is judged by Claude or GPT.
- The rubric starts from SPEC-004 §6.1: terminology 40%, fidelity 35%, fluency 25%. Each score cites the segment it criticises.
- The same source segments are compared across runs: same EPUB, same segmenter, one checkpoint per `(runtime, model_id, effort)`.
- The AI judge is calibrated against the owner: on a shared sample, measure how often the judge agrees with the human verdict before trusting it on whole books.
- SPEC-004 lesson: its A/B test was negative. A comparison needs a fixed corpus and a decision gate written down before the run.

The AGENTS.md note "Codex comparison is deferred" is lifted by this spec.

### 3.8 Supported combinations: named rows, not the Cartesian product

Source principle: research note `2026-11-04_puresubs_static-complexity-review-handoff` ("配置组合：四个不同层次"; "用合法性检查与已验证组合限制实验范围").

The theoretical space is large: 6 runtimes (agy, Codex, Claude Code, Gemini/OpenAI/Anthropic API) × 2 tiers × up to 5 efforts × each runtime's version. That number describes what could be configured, not what is supported. BookWeaver does not test the product, and an untested combination is not valid by default.

The registry is a short list of **named rows**. Each row is one `(runtime, tier, family, effort)` that the owner chose to enable. Anything not in the list is rejected before the run starts, with a message that names the enabled rows.

Each row records which of four layers it has proven. The layers are separate; passing one does not imply the next.

| Layer | Question | Evidence | Who decides |
|---|---|---|---|
| 1. Legal | Do the fields and references exist? | Registry validation at startup | Code |
| 2. Executable | Does the full path run on this runtime version? | Fake-executable contract test per runtime spec + live three-passage probe per `(runtime, version, model_id)` (§3.3) | Code + probe |
| 3. Qualified | Is the output good enough for books? | Fixed-corpus evaluation, human + AI judge (§3.7) | Owner |
| 4. Allowed | May it be used, and how? | `default`, `manual`, or `experiment` status in the row | Owner |

Rules:

- Contract tests cover each **adapter branch** (argv, output parsing, error classes) with one representative row, not every row. The CI note `2026-11-07_devops_how-heavy-should-ci-be` gives the same rule: representative samples per code branch, not the full product.
- Layer 2 live probes run only for enabled rows, and only on a new runtime version (§3.3).
- Layer 3 evaluation runs only for rows the owner wants to promote to `default` or to rely on for a whole book.
- A row with status `experiment` can run, but the run audit marks it as not qualified.
- Adding a row is an explicit change with its evidence. Adding a runtime does not enable every tier and effort on it.
- Quality comparison changes one variable at a time (runtime, model, or effort) against a fixed corpus and prompt; otherwise the result cannot be attributed.

Initial rows (proposal for owner review):

| Runtime | Tier | Family | Effort | Status | Proven to |
|---|---|---|---|---|---|
| antigravity | flash | `gemini-3.8-flash` | low | default | Layer 2 (agy 1.5.3 probe) + one validated book on 1.1.27 |
| antigravity | pro | `gemini-4-argon` | low | experiment | Layer 2 after Phase 1 probe |
| codex | flash / pro | tbd after roster read | tbd | experiment | none yet |
| claude-code | flash / pro | `claude-sonnet-5-5` / `claude-opus-5-5` | low | experiment | none yet |
| anthropic / gemini API | flash / pro | as pinned in SPEC-024 | vendor-pinned | manual (paid) | Layer 2 offline only |

## 4. Out of scope

- Detailed evaluation design (corpus, sample size, judge prompt, agreement threshold): a separate spec after Phase 3.
- Any automatic fallback between runtimes, subscription or metered. A run uses one runtime; switching is an explicit user action, and resume warns on mixed models as today.
- Async batch APIs (previously planned as SPEC-025; renumber to SPEC-027).
- Named rows on the CLI and the local API: SPEC-026, built on the §3.8 registry after Phase 1.

## 5. Open items before implementation

- [ ] Codex: read `codex exec` docs and verify how effort is set (expected `-c model_reasoning_effort=...`, not verified), how the roster is listed, and how to read the final message cleanly (`--output-last-message` or JSON events).
- [ ] Codex: pin flash/pro GPT families after reading the roster on the owner machine.
- [ ] Claude Code: verify `claude -p` with `--model`, `--effort`, `--bare` and a tool lockdown (`--tools ""` or `--disallowedTools`), and confirm it uses subscription login, not an API key.
- [ ] Antigravity: search for a print-mode tool or write restriction.
- [ ] Choose the certification cache location (proposed: the existing runtime state directory beside the user config).

## 6. Phases

1. **Antigravity axis separation + named-row registry (§3.8) + Argon pro + automatic probe.** Fixes both observed failures. Offline tests through the provider boundary with a fake `agy` executable: argv carries the family once and effort once; unknown version triggers probe; probe failure stops before book batches; checkpoint `model_id` is unchanged for existing flash runs.
2. **`SubscriptionCliProvider` extraction.** Antigravity moves onto the shared adapter with no behavior change; same tests stay green.
3. **Codex and Claude Code specs + `runtime` provenance field.** After §5 items are resolved. Fake-executable tests, then one owner-run three-passage probe per runtime.
4. **Evaluation spec, then quality comparison** on one already-validated book: human sample plus cross-vendor AI judge.

## 7. Verification

- `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`, `uv run tach check`.
- Live probes are recorded separately in `docs/plans/`, as in `2026-11-07-antigravity-1.5.3-compatibility-probe.md`.
