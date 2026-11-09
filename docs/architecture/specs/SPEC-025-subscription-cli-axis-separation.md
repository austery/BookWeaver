---
specId: SPEC-025
title: Subscription CLI Runtimes with Separated Model Axes
status: Draft for owner review (2026-11-07)
implementationStatus: Phase 1 implemented and live-verified on agy 1.5.3 (2026-11-07); Phase 2 implemented (2026-11-09); Phase 3 Codex implemented and live-probed on Luna and Sol (2026-11-09); Phase 3 Claude Code implemented and live-probed on Sonnet (2026-11-09), subscription pool not yet confirmed; Phase 4 not started
priority: P1 - Runtime Reliability
creationDate: 2026-11-07
lastUpdateDate: 2026-11-09
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
- The registry maps `(runtime, tier)` to a model **family** plus the owner-enabled efforts. Example: `("antigravity", "flash") -> family "gemini-3.8-flash"`, with one preset per enabled effort (§3.8 table).
- The provider passes effort exactly once, through the runtime's own effort option.
- The runtime still decides whether a `family + effort` pair exists; BookWeaver does not copy the vendor's naming or validity table. The enabled-effort list is a product decision (§3.8), not a copy of vendor rules.
- `ResolvedModel.model_id` keeps the concrete ID (`gemini-3.8-flash-low`) for checkpoint provenance and mixed-model resume warnings. A new `family` field carries the argv value. Existing checkpoints stay compatible.
- Discovery checks that `f"{family}-{effort}"` is in `agy models` and fails loudly otherwise. Runtime-side rejection remains the second guard.

### 3.2 Pro tier (owner decision 2026-11-07)

- `("antigravity", "pro") -> "gemini-4-argon"`.
- It must pass the compatibility probe (§3.3) before release. Gemini 3.1 Pro is retired from the registry.

### 3.3 Version gate: automatic compatibility probe (owner decision 2026-11-07)

The gate guards protocol drift; roster checks already guard model absence.

- Seed certifications are `(version, model_id)` pairs with recorded probe evidence (`CERTIFIED_AGY_MODELS`). A seeded version does not exempt other models: any unseeded pair is probed before its first book batch.
- An uncertified `(version, model_id, protocol)` triggers the probe in the provider package: one call with three synthetic passages through the production framing, invocation and `split_response` path. Translation (`segment_tags`) uses the run's own production prompt and checks protocol only (segment count and order, non-empty, no fences or artifact links inside any segment). An outer Markdown fence around the whole response is not a probe failure: the production parser removes it by design (`_strip_fenced_wrapper` in `ai/adapters/providers/_delimiter.py`), so it does not break translation, because the target language is not known to the provider. Glossary extraction (`delimiter`) uses a fixed Chinese translation prompt and also requires Chinese output, because the extraction prompt returns terms, not translations. No book passages are sent. The run's prompt may carry its glossary terms; they go only to the same runtime that is about to translate the book.
- Pass: record `(runtime, version, model_id, protocol, timestamp, result)` in the user-local certification cache `~/.local/state/bookweaver/runtime-certifications.json` (or `$XDG_STATE_HOME/bookweaver/`), then continue. The cache is the probe record; the run audit records `runtime_version` and `preset_status`. The probe runs per framing protocol, because glossary extraction uses `delimiter` and translation uses `segment_tags`.
- Fail: stop before any book batch, with the probe diagnosis.
- Cost: one short subscription call per new `(version, model_id, protocol)`, so at most two per model. No metered API is ever used for this probe.
- The old version-only `CERTIFIED_AGY_VERSIONS` list is replaced by the per-pair seed `CERTIFIED_AGY_MODELS` above.
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
- Provenance records the runtime as well as the model. Today a checkpoint records `provider: cli` and `model_id`; `claude-opus-5-5` through agy and through Claude Code would be indistinguishable. Record the runtime (`antigravity`, `codex`, `claude-code`) in per-segment provenance, through the existing `backend` field (§5).
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

### 3.8 Supported combinations: named presets, not the Cartesian product

Source principle: research note `2026-11-04_puresubs_static-complexity-review-handoff` ("配置组合：四个不同层次"; "用合法性检查与已验证组合限制实验范围").

The theoretical space is large: 6 runtimes (agy, Codex, Claude Code, Gemini/OpenAI/Anthropic API) × 2 tiers × up to 5 efforts × each runtime's version. That number describes what could be configured, not what is supported. BookWeaver does not test the product, and an untested combination is not valid by default.

The registry is a short list of **named presets**. Each preset is one `(runtime, tier, family, effort)` that the owner chose to enable. Anything not in the list is rejected before the run starts, with a message that names the enabled presets.

Each preset records which of four layers it has proven. The layers are separate; passing one does not imply the next.

| Layer | Question | Evidence | Who decides |
|---|---|---|---|
| 1. Legal | Do the fields and references exist? | Registry validation at startup | Code |
| 2. Executable | Does the full path run on this runtime version? | Fake-executable contract test per runtime spec + live three-passage probe per `(runtime, version, model_id)` (§3.3) | Code + probe |
| 3. Qualified | Is the output good enough for books? | Fixed-corpus evaluation, human + AI judge (§3.7) | Owner |
| 4. Allowed | May it be used, and how? | `default`, `manual`, or `experiment` status in the preset | Owner |

Rules:

- Contract tests cover each **adapter branch** (argv, output parsing, error classes) with one representative preset, not every preset. The CI note `2026-11-07_devops_how-heavy-should-ci-be` gives the same rule: representative samples per code branch, not the full product.
- Layer 2 live probes run only for enabled presets, and only on a new runtime version (§3.3).
- Layer 3 evaluation runs only for presets the owner wants to promote to `default` or to rely on for a whole book.
- A preset with status `experiment` can run, but the run audit marks it as not qualified.
- Adding a preset is an explicit change with its evidence. Adding a runtime does not enable every tier and effort on it.
- Quality comparison changes one variable at a time (runtime, model, or effort) against a fixed corpus and prompt; otherwise the result cannot be attributed.

Initial presets (proposal for owner review):

| Runtime | Tier | Family | Effort | Status | Proven to |
|---|---|---|---|---|---|
| antigravity | flash | `gemini-3.8-flash` | low | default | Layer 2 (agy 1.5.3 probe) + one validated book on 1.1.27 |
| antigravity | flash | `gemini-3.8-flash` | medium, high | experiment | Layer 1; kept for effort comparison (low is the normal choice for translation); probed automatically on first use |
| antigravity | pro | `gemini-4-argon` | low | experiment | Layer 2 (agy 1.5.3 probe, both protocols) |
| antigravity | pro | `gemini-4-argon` | high | experiment | Layer 1; probed automatically on first use |
| codex | flash | `gpt-6-luna` (tier default), `gpt-6.1-terra` | low | experiment | Luna Layer 2 (codex-cli 0.167.0 probe); Terra Layer 1, probed automatically on first use |
| codex | pro | `gpt-6.1-sol` (tier default), `gpt-6-astra` | low | experiment | Sol Layer 2 (codex-cli 0.167.0 probe); Astra Layer 1, probed automatically on first use |
| claude-code | flash / pro | `claude-sonnet-5-5` / `claude-opus-5-5` | low | experiment | none yet |
| anthropic / gemini API | flash / pro | as pinned in SPEC-024 | vendor-pinned | manual (paid) | Layer 2 offline only |

### 3.9 Codex decisions (owner, 2026-11-09)

Evidence comes from running Codex CLI 0.167.0 against a local fake provider, which shows the exact request.

- **Isolation.** `$CODEX_HOME/AGENTS.md` reaches every batch, and `--ignore-user-config`, `project_doc_max_bytes=0` and `agents_md.*` do not remove it. The owner's coding rules must not shape a translation, so BookWeaver uses its own home, `$XDG_STATE_HOME/bookweaver/codex-home`, with its own `codex login`. Copying or linking `auth.json` is rejected: a token refresh in one home can invalidate the other.
- **Fixed context.** The default adds about 36,000 characters to every batch, mostly a coding-agent prompt and a skills list. `model_instructions_file`, `skills.include_instructions=false` and the `include_*_instructions=false` options cut it to about 2,800 characters. A 2,400-character multi-agent note remains; `--disable multi_agent` does not remove it.
- **Selectable models.** The formal choice comes after test rounds, so one tier can hold several models, and the preset table is the selection surface (`--preset`, and the `/docs` dropdown). A tier default answers a bare tier, such as extraction's `pro`. `gpt-6-astra` costs the most, so it is never a tier default and runs only when selected by name. All Codex presets use low effort.
- **Resume.** The checkpoint identity keys on tier and effort, which those models share. A resume that crosses a Codex model stops before any model call unless `--force-resume` is given; otherwise a model test finishes with no call to that model. The identity and the schema do not change. All other changes keep the existing warning, including metered vendor switches (SPEC-024) and retired or legacy models. The local API upload gives each Codex preset its own `<preset>/` folder inside the book's folder, so the dropdown can compare Codex models on one book; other presets keep their existing location.
- **Persistent structures.** `_KNOWN_BACKENDS` gains `codex` (§5). `ai/config_schema.json` gains an optional `codex.timeout_seconds`, mirroring `antigravity.timeout_seconds`.
- **Billing guard.** The child environment drops `OPENAI_API_KEY`, `CODEX_API_KEY`, `CODEX_ACCESS_TOKEN`, `OPENAI_BASE_URL`, `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN`. Discovery stops unless `codex login status` reports a ChatGPT login.

### 3.10 Claude Code decisions (2026-11-09)

Evidence comes from running Claude Code 2.1.311 against a local fake endpoint (`docs/plans/2026-11-09-claude-code-request-capture.md`). The owner then ran one live probe on `claude-sonnet-5-5-low` (`docs/plans/2026-11-09-claude-code-compatibility-probe.md`).

- **Isolation.** Unlike Codex, no private home is needed: `--restricted` keeps the owner's `CLAUDE.md`, auto-memory, skills and plugins out of the request, so the runtime uses the owner's claude.ai login. The help text does not promise this, so the capture must be repeated after a Claude Code upgrade.
- **Fixed context.** `--system-prompt` cuts the fixed context from about 5,700 to about 1,900 characters. One environment message of about 1,100 characters remains.
- **Prompt guards.** A prompt whose first character is `/` stops before the process starts, because Claude Code would run it as a local command. A result with a model-turn count other than one is a failure. The child runs in an empty directory, because `@name` in the prompt inlines a file from the working directory.
- **Billing guard.** The child environment drops every `ANTHROPIC_*` variable, `CLAUDECODE` and every `CLAUDE_*` variable except `CLAUDE_CONFIG_DIR`, plus `OPENAI_API_KEY` and `CODEX_API_KEY`. Discovery stops unless `claude auth status` reports `loggedIn` with `authMethod: claude.ai`.
- **Single attempt.** The child sets `CLAUDE_CODE_MAX_RETRIES=0`. Without it the CLI retried a fake 401 and a fake 429 for more than 100 seconds and printed nothing; with it the result object arrives at once with `api_error_status`. The trade-off: one transient error, such as an overloaded response, stops the run, because `ProviderUnavailableError` halts and is never split or retried. Committed batches stay resumable. The setting does not stop Claude Code from continuing a reply cut at the output cap: against the fake endpoint it sent up to four requests for one prompt.
- **Result checks.** A reply counts only with exactly one model turn and `stop_reason: end_turn`. A reply cut at the output cap raises `OutputTruncatedError`; a refusal or any other stop reason halts. Model output never enters an error message.
- **No roster.** Claude Code has no command that lists models, so the roster step is optional in the shared adapter. `modelUsage` in the result names the requested model even when the endpoint answers with another one, so it is not used as a check. An unknown model fails the probe.
- **Presets (proposed, owner to confirm).** `claude-sonnet-5-5-low` is the flash tier and `claude-opus-5-5-low` is the pro tier, mirroring the metered Anthropic entries. Both are `experiment`; Sonnet is layer 2 after the live probe, and Opus is layer 1. Glossary extraction on a Claude Code run therefore goes to Opus on the coding quota unless `--extraction-model flash` is given.
- **Persistent structures.** `_KNOWN_BACKENDS` gains `claude-code`. `ai/config_schema.json` gains an optional `claude_code.timeout_seconds`.
- **Resume and folders (owner, 2026-11-09).** The Codex rules in §3.9 now cover Claude Code: `TRIAL_CLI_RUNTIMES` in `ai/model_profiles.py` names both runtimes. The reason: `claude-sonnet-5-5-low` shares the flash/low checkpoint identity with the default `agy-flash-low`. Before this rule, a Claude run on a folder with a finished Gemini checkpoint restored every segment with a warning and made no Claude translation call; with term extraction on, it still sent one extraction request to Claude. A resume that crosses a Claude Code model now stops before extraction unless `--force-resume` is given, in both directions and against Codex. The local API upload gives each Claude Code preset its own `<preset>/` folder. Changes within Antigravity and between metered vendors keep their warning.

## 4. Out of scope

- Detailed evaluation design (corpus, sample size, judge prompt, agreement threshold): a separate spec after Phase 3.
- Any automatic fallback between runtimes, subscription or metered. A run uses one runtime; switching is an explicit user action, and resume warns on mixed models as today, except for the Codex and Claude Code cases in §3.9 and §3.10.
- Async batch APIs (previously planned as SPEC-025; renumber to SPEC-027).
- Named presets on the CLI and the local API: SPEC-026, built on the §3.8 registry after Phase 1.

## 5. Open items before implementation

Facts below come from local help text and local files on 2026-11-09 (Codex CLI 0.167.0, Claude Code 2.1.311, agy 1.5.3). Codex then passed a live probe (`docs/plans/2026-11-09-codex-compatibility-probe.md`). Claude Code then ran against a local fake endpoint (`docs/plans/2026-11-09-claude-code-request-capture.md`), which shows the request it builds. No prompt was sent to Anthropic through Claude Code, so its commands are not proven end to end yet.

- [x] Codex flags: `-m <model>`, `-c model_reasoning_effort="<effort>"`, `-s read-only`, `--ephemeral`, `--skip-git-repo-check`, `--ignore-user-config`, `--ignore-rules`, `-C <workspace>`, `-o <file>` for the final message. The prompt can come from stdin. `codex debug models` provides the roster.
- [x] Codex: `exec` runs with `approval_policy="never"`, a read-only sandbox and `--disable shell_tool`; the outer deadline remains the guard against a hang. A live hang test has not run.
- [x] Codex: models pinned in §3.9.
- [x] Claude Code: **do not use `--bare`.** Its help says Anthropic auth is then "strictly ANTHROPIC_API_KEY or apiKeyHelper" and OAuth is never read. It would fail, or bill a key instead of the subscription. This replaces the earlier candidate flag.
- [x] Claude Code flags: `-p --restricted --strict-mcp-config --tools= --no-session-persistence --output-format json --model <family> --effort <effort> --system-prompt <text>`. The capture on 2.1.311 shows that `--restricted` keeps the owner's `CLAUDE.md`, auto-memory, skills and plugins out of the request; its help text promises only that it ignores settings files, so repeat the capture after an upgrade. `--system-prompt` replaces about 4,200 characters of coding-agent prompt and removes git status. `--tools=` replaces `--tools ""`: a lost empty value makes `--tools` swallow the next flag and still exit 0. With no tools the runtime cannot read a prompt file, so the prompt must travel on stdin; the shared adapter needs that input path.
- [x] Claude Code prompt guards (done, §3.10), from the capture: a prompt that starts with `/` runs as a local command, with no request, exit 0, `is_error: false` and `num_turns: 0`, so the spec must reject such a prompt and treat `num_turns: 0` as a failure; `@path` in the prompt inlines a file from the working directory even with no tools, so the working directory must be empty and the prompt file must live elsewhere.
- [ ] Claude Code: an owner-run probe must confirm that `-p` draws on the subscription pool and not on separate credit. Help text cannot prove this. The owner-run probe on 2026-11-09 passed, but the usage comparison that shows which pool paid is still open.
- [x] Subscription guard, Codex side done in §3.9, Claude Code side in §3.10: a key in the environment can silently turn a subscription run into a metered call. The child environment drops `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY` and `CODEX_API_KEY`. The capture confirms the risk for Claude Code: with a key in the environment, every request used the key and not the claude.ai login. The Claude Code child must also drop `ANTHROPIC_BASE_URL`, `CLAUDECODE` and the `CLAUDE_CODE_*` variables that a parent Claude Code session exports; `CLAUDE_CODE_SIMPLE` is the variable `--bare` sets. Discovery stops unless `claude auth status` reports `authMethod: claude.ai`, or `codex login status` reports a ChatGPT login.
- [ ] Antigravity: `agy --help` lists `--sandbox` ("terminal restrictions enabled"). It is not applied yet, because its effect on the prompt-file read is unknown and a change needs a probe.
- [x] Provenance: per-segment `backend` already records the concrete runtime (`ai/ports/provider.py`). Phase 3 adds `codex` (done) and `claude-code` to `_KNOWN_BACKENDS` in `ai/checkpoint_store.py` instead of adding a second field. Claude through agy and through Claude Code then stay distinct.
- [x] Registry: a bare tier means Antigravity unless `resolve_profile` receives a runtime; a named preset resolves through `resolve_preset`, so a new preset cannot take over `--model flash --effort low`.
- [x] Certification cache location: `$XDG_STATE_HOME/bookweaver/runtime-certifications.json`, default `~/.local/state/bookweaver/` (Phase 1). Since Phase 2 a pass counts only for the runtime that earned it.

## 6. Phases

1. **Antigravity axis separation + named-preset registry (§3.8) + Argon pro + automatic probe.** Fixes both observed failures. Offline tests through the provider boundary with a fake `agy` executable: argv carries the family once and effort once; unknown version triggers probe; probe failure stops before book batches; checkpoint `model_id` is unchanged for existing flash runs.
2. **`SubscriptionCliProvider` extraction (done 2026-11-09).** Antigravity moves onto the shared adapter with no behavior change; same tests stay green. One deliberate change: a certification now matches on runtime too, so a record from another runtime no longer counts. Existing records all name `antigravity` and stay valid. `ai/subscription_cli_provider.py` holds the adapter; `ai/antigravity_provider.py` holds the spec.
3. **Codex and Claude Code specs + runtime provenance through `backend`.** After §5 items are resolved. The shared process call gains stdin input and an explicit child environment; a runtime spec returns them with its argv, and no spec starts its own process. Fake-executable tests, then one owner-run three-passage probe per runtime.
4. **Evaluation spec, then quality comparison** on one already-validated book: human sample plus cross-vendor AI judge.

## 7. Verification

- `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`, `uv run tach check`.
- Live probes are recorded separately in `docs/plans/`, as in `2026-11-07-antigravity-1.5.3-compatibility-probe.md` `2026-11-09-codex-compatibility-probe.md` and `2026-11-09-claude-code-compatibility-probe.md`. Offline captures go there too, as in `2026-11-09-claude-code-request-capture.md`.
