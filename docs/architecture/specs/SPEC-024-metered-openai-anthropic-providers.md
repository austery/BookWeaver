---
specId: SPEC-024
title: Metered API Providers through LiteLLM (OpenAI, Anthropic, Gemini)
status: Draft - owner decisions recorded, awaiting final review
implementationStatus: Not started
priority: P2 - Core Feature
creationDate: 2026-11-07
lastUpdateDate: 2026-11-07
owner: User (AI-Assisted)
relatedSpecs: [SPEC-020, SPEC-021, SPEC-022, SPEC-023]
tags:
  - metered-api
  - litellm
  - openai
  - anthropic
  - paid-api-authorization
  - checkpoint-provenance
---

# SPEC-024: Metered API Providers through LiteLLM

## 1. Goal

Let the owner translate EPUB books through the Anthropic and OpenAI APIs. The owner has prepaid API credit with both vendors, and that credit cannot be spent through their subscription CLIs.

The design constraint is complexity. Vendor and call-layer differences are accidental complexity: the market is fragmented, and a maintained library already absorbs that. BookWeaver keeps only the essential parts in its own code: paid authorization, cost evidence, truncation handling, and checkpoint provenance. The vendor glue goes to LiteLLM, a documented and widely used library, instead of being written here.

SPEC-020's billing rules are unchanged: no automatic paid fallback, explicit per-invocation authorization, and one network attempt per planned batch. Antigravity remains the default runtime.

## 2. Owner decisions (2026-11-07)

| # | Question | Decision |
|---|---|---|
| D1 | Implementation shape | **One LiteLLM-backed metered provider** for every API vendor. The Gemini path moves onto it too. No new port and no per-vendor transport |
| D2 | Provider naming | `--provider cli \| gemini \| openai \| anthropic`. `api` is removed from the CLI with an explicit error. Checkpoints keep accepting stored `api` as legacy Gemini |
| D3 | Anthropic profiles | `flash` → Sonnet, `pro` → Opus |
| D4 | Truncation | Stop; no automatic extra paid request (owner asked what this meant, §8 explains it; the recommended stop behavior is recorded) |
| D5 | Batch size | Check the limits first. Verified Anthropic limits allow the current defaults, so API runs use the **same** 60,000 characters / 200 segments as Antigravity |
| D6 | Custom `base_url` | Out of scope |
| D7 | Async batch APIs | Yes, as a separate follow-up spec, not here |

## 3. Evidence

### 3.1 Vendor limits

Source: Anthropic models overview, read 2026-11-07 at `platform.claude.com/docs/en/about-claude/models/overview`.

| Model | API ID | Max output | Price (input / output per MTok) |
|---|---|---|---|
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | 128K tokens | $2 / $10 |
| Claude Opus 5.5 | `claude-opus-5-5` | 128K tokens | $4 / $20 |

- The same docs say the SDK requires streaming for large `max_tokens` values, to avoid HTTP timeouts.
- Default effort is `medium` (Opus 5.5) and `high` (Sonnet 5.5).
- Prompt caching needs at least 512 tokens.

OpenAI limits are **not yet verified**: the documentation host was unreachable from the drafting environment. The OpenAI mapping stays empty until §6.2 is filled from vendor documentation.

### 3.2 Why the current batch size fits

A 60,000-character English batch translates into roughly 20k–27k output tokens of Chinese, including segment tags. That is an estimate, and §11 Phase 2 replaces it with measured values. A 128K output cap leaves more than 4x margin. API runs therefore need no separate batch defaults.

With few, large requests per book (about ten for a 500,000-character book), repeating the system prompt costs little. Prompt caching is out of scope.

### 3.3 Library check

Inspected LiteLLM 1.108.2 in an isolated environment on 2026-11-07:

- It maps Anthropic `stop_reason: max_tokens` to `finish_reason: "length"`.
- It parses Anthropic cache usage.
- It exposes `num_retries`.

Cost of adoption: about 60 installed packages and about 230 MB in site-packages. Mitigations: an exact version pin in `uv.lock`, and an import only when a metered provider is selected.

### 3.4 Open-source survey

Two open-source translators were surveyed: read-frog and bilingual_book_maker.
- Both route providers through a shared abstraction rather than per-vendor code paths. bilingual_book_maker includes a LiteLLM route.
- bilingual_book_maker's hand-built per-vendor code (about 2,300 lines for its OpenAI translator, plus about 380 lines of batch collect/replay) shows the growth this spec avoids.

## 4. Scope

In scope:

- Replace the Gemini-only `_PaidProvider` in `ai/runtime_factory.py` with one LiteLLM-backed metered provider.
- Provider rename (D2), model registry entries, authorization text, truncation error, checkpoint provenance values, and `backend` reporting.
- One optional configuration key for request timeout.

Non-goals:

- Subscription CLI runtimes (Codex CLI, Claude Code CLI).
- Vendor async batch APIs (follow-up spec, D7).
- Prompt caching, custom `base_url`, and structured output.
- Prompt or segment-protocol changes.
- Per-API batch defaults.
- Concrete model names on the CLI.
- Live tests in CI.
- Extending legacy modules: `ai/gemini_api_provider.py`, `ai/provider_factory.py`, `ai/adapters/providers/gemini_api_adapter.py`, and the historical helpers in `ai/orchestration.py`.

## 5. CLI contract

```text
--provider cli         Antigravity; default; subscription
--provider gemini      Gemini API; metered
--provider openai      OpenAI API; metered
--provider anthropic   Anthropic API; metered
```

- `--provider api` fails during argument handling: `"--provider api was renamed; use --provider gemini"`.
- `--model flash|pro` stays the only model selector.
- `--allow-paid-api` authorizes any metered provider and stays invalid with `cli`.
- `--effort` with a metered provider fails before construction, as today. The registry pins the API effort (§6.2).
- The parser description no longer says "through Antigravity" only.

```bash
uv run bookweaver book.epub --output book.zh.epub --provider anthropic --model flash --allow-paid-api
```

## 6. Model registry (`ai/model_profiles.py`)

### 6.1 Provider identity

- `ProviderName` becomes `cli | gemini | openai | anthropic`.
- One predicate, `is_metered(provider)`, is true for everything except `cli`. Application code uses it instead of comparing with `"api"`.

### 6.2 Pinned API mappings

One table, keyed by `(provider, profile)`, gives the LiteLLM model string, the requested output cap, and the pinned effort. Every row cites its source and read date.

| Provider | Profile | LiteLLM model | Output cap | Effort | Source |
|---|---|---|---|---|---|
| anthropic | flash | `anthropic/claude-sonnet-5-5` | 128,000 | low (see §12 item 2) | §3.1 |
| anthropic | pro | `anthropic/claude-opus-5-5` | 128,000 | low (see §12 item 2) | §3.1 |
| gemini | flash | `gemini/gemini-2.5-flash` | fill from vendor docs | none | to cite in implementation |
| gemini | pro | `gemini/gemini-2.5-pro` | fill from vendor docs | none | to cite in implementation |
| openai | flash / pro | **unfilled** | — | — | blocked on §3.1 |

- A provider with no filled row fails before any request: `"No pinned openai model for profile flash; update ai/model_profiles.py with cited limits"`.
- `ResolvedModel` gains `output_cap: int | None` and `api_effort: str | None`. Both are `None` for `cli`.
- `effort` stays the Antigravity user axis.

## 7. Architecture

### 7.1 Metered provider

`_PaidProvider` in `ai/runtime_factory.py` becomes `_MeteredProvider`, still about one screen of code. It keeps today's audit and error sequence:

1. Frame the batch with the existing `_delimiter` helpers: `augment_prompt_for_batch` into the system message, `join_segments` into the user message. The prompt and protocol stay as they are.
2. Append a pending `RequestUsage` and persist the audit.
3. Call `litellm.completion(model=..., messages=..., max_tokens=output_cap, stream=True, stream_options={"include_usage": True}, num_retries=0, max_retries=0, timeout=...)` exactly once, plus the pinned effort parameter. Assemble the final response from the stream.
   - Streaming is used for every vendor, so there is one code path.
   - The SDK-retry and LiteLLM-retry arguments are asserted in tests.
4. Record input and output tokens, and persist the audit.
5. Translate errors (§8). If `finish_reason == "length"`, raise `OutputTruncatedError`. Raise on empty text.
6. Otherwise return `split_response(...)`.

`_MeteredProvider.backend = "litellm"` and `runtime_version = None`. `ITranslationProvider` gains `backend: str | None = None`, mirroring `runtime_version`. `AntigravityProvider` sets `"antigravity"`.

`litellm` is imported inside `_MeteredProvider.__init__` only. `pyproject.toml` adds `litellm` with an exact pin. `google-genai` stays a dependency until the legacy modules that import it are retired.

### 7.2 Factory and authorization

- The `DefaultProviderFactory.create` branch changes from `model.provider == "api"` to `is_metered(model.provider)`. The SPEC-020 rules stay as they are:
  - one consent per invocation, covering glossary extraction and translation;
  - interactive confirmation or `--allow-paid-api`;
  - configuration never authorizes.
- The confirmation names the vendor and model: `Metered Anthropic API: claude-sonnet-5-5; remaining source approximately N characters ...`.
- Keys come from the standard environment variables `GEMINI_API_KEY`, `OPENAI_API_KEY`, and `ANTHROPIC_API_KEY`. The existing `gemini_api.api_key` config value is still honored for Gemini, so current user configuration keeps working. A missing key fails before any request and names the variable.
- `usage_snapshot()` reports when the runtime provider is metered.

### 7.3 Orchestration (new application path only)

- `model.provider == "api"` becomes `is_metered(model.provider)` for split depth (metered split depth stays 0) and for usage snapshots.
- The segment `backend` comes from the active provider's `backend` attribute instead of `"antigravity" if cli else "gemini_api"`.
- Batch size resolution is unchanged.

## 8. Truncation and failure policy

**Truncation.** Every model has a maximum output length per request. If a translation reaches it, the vendor cuts the reply off and reports that it stopped because of the length limit. The rest of that batch's translation is missing. Two responses were possible:

- **stop**: the chosen behavior. Earlier batches are already in the checkpoint. BookWeaver halts with a message suggesting a smaller `--max-batch-chars`, and the next run resumes.
- **split and resend**: this would spend money without consent.

With more than 4x margin (§3.2), truncation should be rare.

| LiteLLM outcome | Port error | Action |
|---|---|---|
| `AuthenticationError`, `PermissionDeniedError` | `ProviderAuthenticationError` | stop |
| `RateLimitError` (rate or credit) | `RateLimitError` | stop |
| `Timeout`, `APIConnectionError`, `ServiceUnavailableError`, `InternalServerError` | `ProviderUnavailableError` | stop |
| `finish_reason == "length"` | `OutputTruncatedError` (new, subclass of `ProviderUnavailableError`) | stop, suggest smaller batch |
| wrong segment count / malformed tags | `TranslationError` | stop (metered split depth 0) |
| empty content or refusal | `ProviderUnavailableError` | stop |
| any other exception | `ProviderUnavailableError` | stop |

Error messages never include request or response text.

## 9. Configuration

- `ai/config_schema.json` adds one optional section: `"api": {"timeout_seconds": number > 0, <= 86400}`. The default is 600 seconds per request, matching today's Gemini value.
- `gemini_api.api_key` stays accepted.
- No other new keys. Unknown keys still fail loudly. User configuration is never rewritten.

## 10. Checkpoint and audit

- **Provenance validator** (`ai/checkpoint_store.py`):
  - `provider` accepts `cli | api | gemini | openai | anthropic | legacy_unknown`. `api` remains readable as historical Gemini and is never written again.
  - `backend` adds `litellm`.
  - Without this change, a metered run's checkpoint would fail to load on resume (`Invalid checkpoint provenance`).
- **Identity**: `CheckpointIdentity` is unchanged. Provider and concrete model remain audit-only (SPEC-020 §9.2). Because batch sizes are now shared, switching vendors mid-book resumes normally and prints the existing "Mixed-model continuation" notice.
- **Audit** (`.bookweaver_runs/<run_id>.json`):
  - `RequestUsage` gains `provider`.
  - `usage_scope` becomes `"metered_api_requests"`.
  - No keys, prompts, or responses are recorded.

## 11. Phases

**Phase 1: Implementation (offline; mocks at the `litellm.completion` boundary)**

- Registry, rename, `_MeteredProvider`, error mapping, provenance, `backend`, config key, dependency pin, and Tach.
- Gemini behavior is carried over: the existing runtime-factory and invocation-audit tests are adapted to the LiteLLM boundary.
- Update the `README.md`, `CLAUDE.md`/`AGENTS.md`, and `config/config.json.example` pointers.

**Phase 2: Authorized probe (requires separate owner authorization)**

- One short chapter each on Anthropic `flash` and `pro`. Record real output-token ratios, cost, and wall time in `docs/plans/`, separately from mocked tests.
- Confirm or revise §3.2. This is calibration, not book acceptance.

**Phase 3: OpenAI mapping**

- Fill §6.2 from vendor documentation with a citation, then run the same probe under authorization.

## 12. Items to verify in Phase 1

1. **Streaming usage.** Assembling the streamed Anthropic and Gemini responses through LiteLLM yields input and output token counts and `finish_reason`. If not, record usage as `None`, never as `0`.
2. **Effort.** How LiteLLM passes Anthropic effort for these models. If it cannot pin `low`, record the vendor default and its cost implication instead of hand-writing a vendor request.
3. **Retries.** `num_retries=0` and `max_retries=0` produce exactly one HTTP attempt. Assert it with a mocked transport.

## 13. Acceptance criteria

- [ ] `--provider api` fails with the rename message. `gemini`, `openai`, and `anthropic` are accepted.
- [ ] Each metered provider requires `--allow-paid-api` when non-interactive. Configuration cannot authorize. One consent covers glossary extraction plus translation.
- [ ] `--allow-paid-api` with `cli`, and `--effort` with a metered provider, fail before construction.
- [ ] An unfilled registry row (OpenAI) fails before any request with the registry message.
- [ ] Exactly one `litellm.completion` call per planned batch, with retries disabled.
- [ ] `finish_reason == "length"` raises `OutputTruncatedError`, persists the audit as failed, and leaves earlier checkpoint batches intact.
- [ ] Each row of §8 maps as specified.
- [ ] A checkpoint written by an `anthropic` run reloads with `provider: anthropic`, `backend: litellm`. A checkpoint with historical `provider: api` still loads.
- [ ] Usage reaches the audit file and the checkpoint usage summary. Unknown usage stays `None`.
- [ ] `litellm` is not imported when `--provider cli` is used.
- [ ] `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`, and `uv run tach check` pass.

## 14. Risks

| Risk | Mitigation |
|---|---|
| Heavy, fast-moving dependency | Exact pin in `uv.lock`; lazy import; upgrades only through a deliberate PR |
| LiteLLM normalization hides a vendor behavior | §12 checks before relying on it; usage stays `None` when unknown |
| Truncation on unusually expansive text | >4x margin; explicit stop; user lowers `--max-batch-chars` |
| Mid-book vendor switch changes voice | Existing mixed-model notice; provenance per segment |
| Spend surprises | Per-invocation authorization with remaining-character estimate; audit persisted even on failure |

## 15. Follow-up

- **SPEC-025 (planned):** vendor async batch APIs. Anthropic documents 50% pricing and up to 300K output tokens for Message Batches. The spec must define how submit, poll, and collect fit the checkpoint store without building a parallel batch framework. It should first check whether LiteLLM's batch support covers both vendors.

## 16. Status history

- 2026-11-07: First draft (native SDK transports).
- 2026-11-07: Rewritten after owner review: LiteLLM single provider, provider rename, current batch defaults, caching and `base_url` removed, async batches deferred to SPEC-025.
