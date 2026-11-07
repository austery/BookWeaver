---
specId: SPEC-024
title: Metered API Providers through any-llm (Anthropic, OpenAI, Gemini)
status: Approved by owner (2026-11-07)
implementationStatus: Phase 1 implemented and verified offline; Phase 2 probe not authorized yet
priority: P2 - Core Feature
creationDate: 2026-11-07
lastUpdateDate: 2026-11-07
owner: User (AI-Assisted)
relatedSpecs: [SPEC-020, SPEC-021, SPEC-022, SPEC-023]
tags:
  - metered-api
  - any-llm
  - openai
  - anthropic
  - paid-api-authorization
  - checkpoint-provenance
---

# SPEC-024: Metered API Providers through any-llm

## 1. Goal

Let the owner translate EPUB books through the Anthropic and OpenAI APIs. The owner holds prepaid API credit with both vendors, and that credit cannot be spent through the vendors' subscription CLIs.

The design constraint is complexity. Vendor and call-layer differences are accidental complexity; a maintained library already absorbs them. BookWeaver keeps only the essential parts in its own code:

- paid authorization;
- cost evidence;
- truncation handling;
- checkpoint provenance.

Vendor glue is delegated to a documented library instead of being written here.

SPEC-020's billing rules are unchanged:

- no automatic paid fallback;
- explicit per-invocation authorization;
- one network attempt per planned batch.

Antigravity remains the default runtime.

## 2. Owner decisions (2026-11-07)

| # | Question | Decision |
|---|---|---|
| D1 | Implementation shape | **One metered provider on [any-llm](https://github.com/mozilla-ai/any-llm)** (`any-llm-sdk`) for every API vendor. The Gemini path moves onto it too. No new port and no per-vendor transport. LiteLLM was chosen first and replaced after the review in §3.3 |
| D2 | Provider naming | `--provider cli \| gemini \| openai \| anthropic`. `api` is removed from the CLI with an explicit error. Checkpoints still accept stored `api` as historical Gemini provenance |
| D3 | Anthropic profiles | `flash` → Sonnet, `pro` → Opus |
| D4 | Truncation | Stop; no automatic extra paid request |
| D5 | Batch size | Limits were checked first. Verified Anthropic limits allow the current defaults, so API runs use the **same** 60,000 characters / 200 segments as Antigravity |
| D6 | Custom `base_url` | Out of scope |
| D7 | Async batch APIs | Yes, in a separate follow-up spec |

## 3. Evidence

### 3.1 Vendor limits

Source: Anthropic models overview, read 2026-11-07 at `platform.claude.com/docs/en/about-claude/models/overview`.

| Model | API ID | Max output | Price (input / output per MTok) |
|---|---|---|---|
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | 128K tokens | $2 / $10 |
| Claude Opus 5.5 | `claude-opus-5-5` | 128K tokens | $4 / $20 |

Other notes from the same docs:

- The SDK requires streaming for large `max_tokens`.
- Default effort is `medium` for Opus 5.5 and `high` for Sonnet 5.5.
- Prompt caching needs at least 512 tokens.

Unverified limits:

- **OpenAI** limits are not verified: `platform.openai.com` was unreachable from the implementation environment. The OpenAI mapping stays empty.
- **Gemini** output cap: 65,536 tokens, taken from LiteLLM 1.108.2's bundled model map. It has not been checked against `ai.google.dev`, which was also unreachable.

### 3.2 Why the current batch size fits

- A 60,000-character English batch should translate into roughly 20k–27k output tokens of Chinese, including segment tags. This is an estimate until the Phase 2 probe measures it.
- Anthropic's 128K cap leaves more than 4x margin. Gemini's 65,536 cap leaves more than 2x.
- With about ten requests for a 500,000-character book, the repeated system prompt is a small cost. Prompt caching is out of scope.

### 3.3 Library choice

Two candidates were evaluated by installing them in isolated environments, inspecting their source, and running them against an offline local fake Anthropic endpoint.

| | LiteLLM 1.108.2 | any-llm-sdk 1.46.0 (chosen) |
|---|---|---|
| Install footprint | ~60 packages, ~231 MB, bundled native extension | ~47 packages, ~90 MB; core is the official vendor SDKs |
| Request shape on Anthropic: `max_tokens` 128,000, `stream: true`, `output_config.effort: low`, no `thinking` | verified | verified |
| Text and usage assembled from the stream | verified | verified (120 input / 42 output tokens) |
| Output-cap stop reported as `length` | verified | verified |
| Exactly one HTTP attempt on 401 / 429 / 5xx | verified (`num_retries=0`, `max_retries=0`) | verified (`max_retries=0` on the client) |
| Typed errors | verified | verified with `unified_exceptions=True`: `AuthenticationError`, `RateLimitError`, `ProviderError` |
| Error text includes source text | no | no |
| Global switches that can change behavior | `LITELLM_DROP_PARAMS` can silently drop `output_config`; global retry and fallback settings | per-instance options |
| Network at import | fetches a remote model-cost map unless `LITELLM_LOCAL_MODEL_COST_MAP=True` | none observed |
| Release provenance | none on PyPI; versions 1.82.7 and 1.82.8 were reported compromised in March 2026 (secondary sources: NetSPI, CraftedSignal) | PyPI Trusted Publishing attestations |

Other options surveyed:

- aisuite, Simon Willison's `llm`, Pydantic AI, instructor, Portkey, and OpenRouter were rejected. The reasons include masked truncation, no way to disable retries, inconsistent errors, async-only APIs, and an extra hosted party.
- A hand-written adapter over the three official SDKs was ranked about equal to any-llm. It was rejected under D1 because it reintroduces per-vendor glue.

### 3.4 Open-source survey

read-frog and bilingual_book_maker both route providers through a shared abstraction. bilingual_book_maker shows the growth this spec avoids: about 2,300 lines for its hand-built OpenAI translator, plus about 380 lines of batch collect/replay code.

## 4. Scope

**In scope:**

- Replace the Gemini-only `_PaidProvider` in `ai/runtime_factory.py` with one any-llm metered provider.
- Provider rename (D2), registry entries, authorization text, and a truncation error.
- Checkpoint provenance values and `backend` reporting.
- One optional configuration key, `api.timeout_seconds`.
- The standalone `00_extract_glossary.py` uses the same provider names.

**Non-goals:**

- Subscription CLI runtimes (Codex CLI, Claude Code CLI).
- Vendor async batch APIs (D7).
- Prompt caching, custom `base_url`, and structured output.
- Prompt or protocol changes, and per-API batch defaults.
- Concrete model names on the CLI.
- Live tests in CI.
- Extending the legacy modules: `ai/gemini_api_provider.py`, `ai/provider_factory.py`, `ai/adapters/providers/gemini_api_adapter.py`, and the historical helpers in `ai/orchestration.py`.

## 5. CLI contract

```text
--provider cli         Antigravity; default; subscription
--provider gemini      Gemini API; metered
--provider openai      OpenAI API; metered (fails until §6.2 has a cited row)
--provider anthropic   Anthropic API; metered
```

- `--provider api` fails with `--provider api was renamed; use --provider gemini`.
- `--model flash|pro` stays the only model selector.
- `--allow-paid-api` authorizes any metered provider. It stays invalid with `cli`.
- `--effort` with a metered provider fails before construction.

```bash
uv run bookweaver book.epub --output book.zh.epub --provider anthropic --model flash --allow-paid-api
```

## 6. Model registry (`ai/model_profiles.py`)

### 6.1 Provider identity

- `ProviderName` is `cli | gemini | openai | anthropic`.
- `is_metered(provider)` is true for everything except `cli`. Application code uses it instead of comparing with `"api"`.

### 6.2 Pinned API mappings

| Provider | Profile | Model ID | Output cap | Effort | Source |
|---|---|---|---|---|---|
| anthropic | flash | `claude-sonnet-5-5` | 128,000 | low | §3.1 |
| anthropic | pro | `claude-opus-5-5` | 128,000 | low | §3.1 |
| gemini | flash | `gemini-2.5-flash` | 65,536 | none | §3.1 (library map, unverified) |
| gemini | pro | `gemini-2.5-pro` | 65,536 | none | §3.1 (library map, unverified) |
| openai | flash / pro | **unfilled** | — | — | blocked |

- A provider without a row fails before any request: `No pinned openai model for profile flash; update ai/model_profiles.py with cited limits`.
- `ResolvedModel` gains `output_cap` and `api_effort`. Both are `None` for `cli`.

## 7. Architecture

### 7.1 Metered provider

`_MeteredProvider` in `ai/runtime_factory.py` replaces `_PaidProvider`.

- **Construction:** `AnyLLM.create(provider, api_key=..., unified_exceptions=True, max_retries=0)`. `any_llm` is imported only here.
- **Per batch:**
  1. Frame the batch with the existing `_delimiter` helpers: system message and user message.
  2. Record a pending `RequestUsage` and persist the audit.
  3. Make exactly one `completion(model=..., messages=..., max_tokens=output_cap, stream=True, stream_options={"include_usage": True}, timeout=...)` call, plus `output_config={"effort": ...}` when the row pins an effort. Text, finish reason, and usage are collected from the stream.
- **After the call:**
  - Errors map per §8.
  - A `length` finish raises `OutputTruncatedError` and records the request as `truncated`.
  - Empty text raises an error.
  - Otherwise the provider returns `split_response(...)`.
- **Provenance:** `backend = "any_llm"`. `ITranslationProvider` gains `backend: str | None = None`, and `AntigravityProvider` sets `"antigravity"`.
- **Test seam:** an `api_base` constructor argument exists only for offline tests. It is not user configuration.

### 7.2 Factory and authorization

- `DefaultProviderFactory.create` branches on `is_metered`. SPEC-020's consent rules are unchanged: one consent per invocation, which covers glossary extraction too.
- The consent message names the vendor and model, for example `Metered Anthropic API: claude-sonnet-5-5; ...`.
- API keys come from `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`. `gemini_api.api_key` is still honored for Gemini.
- A missing key fails before any request and names the variable.

### 7.3 Orchestration

- `is_metered` replaces the `"api"` checks for split depth (0 for metered providers), usage snapshots, and `--allow-paid-api` validation.
- The segment `backend` comes from the active provider. If the provider reports none, it falls back to `antigravity` for `cli` and `any_llm` for metered providers.

## 8. Failure policy

Truncation means the model reached its output cap and the vendor cut the reply off, so the rest of that batch is missing. Earlier batches are already checkpointed. BookWeaver stops and suggests a smaller `--max-batch-chars`. Splitting and resending would spend money without consent (D4).

| any-llm outcome | Port error | Action |
|---|---|---|
| `AuthenticationError` | `ProviderAuthenticationError` | stop |
| `RateLimitError` | `RateLimitError` | stop |
| any other exception (`ProviderError` for 5xx / overload, timeouts, invalid request) | `ProviderUnavailableError` | stop |
| finish reason `length` | `OutputTruncatedError` (subclass of `ProviderUnavailableError`) | stop, suggest smaller batch |
| wrong segment count / malformed tags | `TranslationError` | stop (metered split depth is 0) |
| empty text | `ProviderUnavailableError` | stop |

Error messages never include request or response text. The original exception is kept as `__cause__`.

## 9. Configuration

- `ai/config_schema.json` adds `"api": {"timeout_seconds": number > 0, <= 86400}`. The default is 600 seconds.
- `gemini_api.api_key` stays accepted. No other new keys are added.
- Configuration can never authorize spending.

## 10. Checkpoint and audit

- Provenance values:
  - `provider` accepts `cli | api | gemini | openai | anthropic | legacy_unknown`. `api` is never written again.
  - `backend` adds `any_llm`.
- `CheckpointIdentity` is unchanged. Provider and model are audit-only (SPEC-020 §9.2). Batch sizes are shared across providers, so a vendor switch mid-book resumes normally with the existing mixed-model notice.
- Audit files:
  - `RequestUsage` gains `provider`. Its `state` can be `pending`, `responded`, `truncated`, or `failed`.
  - `usage_scope` is `metered_api_requests`.

## 11. Phases

**Phase 1 — implementation (offline): done 2026-11-07.**
Verification:

- `uv run ruff check .`, `uv run ruff format --check .`, and `uv run tach check` pass.
- `uv run pytest -q`: 692 passed, 1 skipped. Pre-change baseline: 659 passed, 1 skipped.

**Phase 2 — authorized probe (requires separate owner authorization).**

- Run one short chapter on Anthropic `flash` and `pro`.
- Record the output/source token ratio, cost, and wall time in `docs/plans/`, separately from mocked tests.
- Confirm or revise §3.2.

**Phase 3 — OpenAI mapping.**

- Fill §6.2 from vendor documentation with a citation.
- Run the same probe under authorization.

## 12. Phase 1 verification notes

1. **Request shape and streaming** were verified against an offline local fake Anthropic endpoint, with any-llm making real HTTP requests. `tests/unit/test_metered_provider.py` keeps this as a regression guard for library upgrades.
2. **Effort** is passed as Anthropic-native `output_config.effort`. any-llm's `reasoning_effort` default (`auto`) adds nothing to the request, and extended thinking stays off.
3. **Retries:**
   - Anthropic: one HTTP attempt per failure, verified.
   - Gemini: single-attempt behavior was inspected in source only. any-llm maps `max_retries=0` to `retry_options.attempts=1`, and the per-request timeout does not add retries.
   - OpenAI: not exercised, because no OpenAI model is pinned.
4. **Dependency side effect:** any-llm's Gemini extra requires `google-genai>=2.17`. The lock moved from the 1.x line to 3.0.0. The legacy Gemini modules' tests still pass.

## 13. Acceptance criteria

- [x] `--provider api` fails with the rename message. `gemini`, `openai`, and `anthropic` are accepted by `bookweaver` and `00_extract_glossary.py`.
- [x] Non-interactive metered runs require `--allow-paid-api`. Configuration cannot authorize. One consent covers glossary extraction plus translation.
- [x] `--allow-paid-api` with `cli`, `--effort` with a metered provider, and an unpinned OpenAI row all fail before construction.
- [x] Exactly one completion call per planned batch. The client is created with `max_retries=0` and `unified_exceptions=True`.
- [x] Truncation raises `OutputTruncatedError` and records the request as `truncated` with its usage.
- [x] 401 → authentication, 429 → rate limit, 529 → unavailable. Each is a single attempt, and no source text appears in errors.
- [x] An `anthropic` checkpoint reloads with `provider: anthropic` and `backend: any_llm`. Historical `provider: api` checkpoints still load.
- [x] Usage reaches the audit file and the checkpoint usage summary.
- [x] `any_llm` is not imported on the `cli` path.
- [x] Ruff, format, Tach, and the full offline suite pass.
- [ ] Phase 2 probe evidence (requires authorization).

## 14. Risks

| Risk | Mitigation |
|---|---|
| Young, fast-moving dependency | Exact pin plus `uv.lock`; offline contract tests in `tests/unit/test_metered_provider.py` |
| Library normalization hides a vendor behavior | Contract tests assert the raw request body and the stream outcome |
| Truncation on unusually expansive text | >2x–4x margin; explicit stop; user lowers `--max-batch-chars` |
| Gemini single-attempt not exercised over HTTP | Source-inspected (§12); add a fake Gemini endpoint if Gemini becomes a primary path |
| Spend surprises | Per-invocation consent with remaining-character estimate; audit persisted even on failure |

## 15. Follow-up

- **SPEC-025 (planned):** vendor async batch APIs. Anthropic documents 50% pricing and up to 300K output tokens for Message Batches. Check whether any-llm's batch API covers both vendors before designing checkpoint integration.

## 16. Status history

- 2026-11-07: First draft (native SDK transports).
- 2026-11-07: Rewritten after owner review: one LiteLLM provider, provider rename, current batch defaults.
- 2026-11-07: Owner approved implementation. After a library survey, the owner chose any-llm over LiteLLM because of supply-chain provenance, footprint, and global-switch risk. Phase 1 implemented and verified offline.
