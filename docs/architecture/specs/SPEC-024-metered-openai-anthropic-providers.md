---
specId: SPEC-024
title: Metered OpenAI and Anthropic API Providers
status: Draft - awaiting owner review
implementationStatus: Not started
priority: P2 - Core Feature
creationDate: 2026-11-07
lastUpdateDate: 2026-11-07
owner: User (AI-Assisted)
relatedSpecs: [SPEC-020, SPEC-021, SPEC-022, SPEC-023]
tags:
  - metered-api
  - openai
  - anthropic
  - paid-api-authorization
  - prompt-caching
  - checkpoint-provenance
---

# SPEC-024: Metered OpenAI and Anthropic API Providers

## 1. Goal

Let the owner translate EPUB books through the OpenAI API and the Anthropic API. The owner holds prepaid API credit with both vendors that cannot be spent through their subscription CLIs, so this adds metered API transports, not CLI runtimes.

The change extends SPEC-020's single metered path (Gemini API) to a family of metered providers that share one authorization, audit, and failure policy. Antigravity remains the default runtime. SPEC-020's billing and retry rules are unchanged: no automatic paid fallback, explicit per-invocation authorization, one network attempt per planned batch.

## 2. Review gate

This document is a draft. Implementation starts only after the owner approves it and settles §13 (open decisions). No live API call is authorized by this spec; §11 Phase 3 requires a separate authorization.

## 3. Research basis

Observed on 2026-11-07 from shallow clones of two open-source bilingual translators. Upstream code changes; treat this as design input, not a contract.

| Topic | read-frog (`mengxi-ream/read-frog`, browser extension) | bilingual_book_maker (`yihong0618/bilingual_book_maker`, EPUB) |
|---|---|---|
| Provider selection | Vercel AI SDK; native package per major vendor, `openai-compatible` for the rest | Chosen by **wire format**: `openai` and `anthropic`; `--api_base` points either at any host speaking that shape. Gemini and Qwen keep native routes because their features do not reduce to the OpenAI shape |
| Batch size | Default 1,000 characters / 4 paragraphs per request, `%%` separator | Token-budget grouping (`--accumulated_num`), `@@` separator, "output EXACTLY N translations" |
| Count mismatch | Retry, then fall back to per-paragraph requests | Loader repairs misalignment paragraph by paragraph |
| Truncation | Not observed | Rejects replies with `finish_reason == "length"` |
| Cost controls | None observed | Anthropic `cache_control: ephemeral` on the system prompt; optional Anthropic Message Batches (`--batch-api`, half price); `max_tokens` 4,096 |
| Prompt | Short immersive-translation rules (same lineage as BookWeaver's `_SYSTEM_PROMPT_TEMPLATE`) | Short user template plus batch instruction |

Conclusions used below:

1. Two wire formats (OpenAI-shape, Anthropic-native) cover the requested vendors with two small transports. A generic "OpenAI-compatible for everything" route would lose Anthropic prompt-cache control, batch pricing, and usage detail.
2. Both projects send batches one to two orders of magnitude smaller than BookWeaver's Antigravity default (60,000 characters / 200 segments). That default exists because each Antigravity call has process and subscription-quota overhead. Metered APIs bill by token, so smaller batches cost about the same, stay clear of output-token caps, and lose less when one request fails.
3. BookWeaver's prompt is already concise. This spec does not change prompt text.

## 4. Scope

In scope:

- An internal metered-provider shell shared by Gemini, OpenAI, and Anthropic.
- OpenAI transport (official endpoint) and Anthropic transport (native Messages API).
- CLI provider values, configuration sections, authorization text, audit fields, checkpoint provenance values, metered batch defaults, and truncation detection.
- Moving the existing Gemini `_PaidProvider` onto the shell without behavior change.
- Optional later phase: a configurable OpenAI-shape `base_url` (§11 Phase 4).

Non-goals:

- Codex CLI, Claude Code CLI, or any other subscription CLI runtime.
- Vendor asynchronous batch APIs (Anthropic Message Batches, OpenAI Batch). They need their own checkpoint integration and get a separate spec.
- Explicit `--effort` for metered providers, structured/JSON output modes, prompt text changes, automatic provider fallback, concrete model names on the CLI, and live tests in CI.
- Extending legacy modules: `ai/gemini_api_provider.py`, `ai/provider_factory.py`, `ai/adapters/providers/gemini_api_adapter.py`, and the historical helpers in `ai/orchestration.py`.

## 5. Public CLI contract

```text
--provider cli         Antigravity; default; subscription
--provider api         Gemini API; metered (unchanged name, kept for checkpoint compatibility)
--provider openai      OpenAI API; metered
--provider anthropic   Anthropic API; metered
```

- `--model flash|pro` remains the only model selector. Each metered vendor maps both profiles to pinned model IDs (§6.2).
- `--allow-paid-api` authorizes any metered provider and stays invalid with `--provider cli`.
- `--effort` with a metered provider fails before any request, as today.
- The parser description stops saying "through Antigravity" only.

Example:

```bash
uv run bookweaver book.epub --output book.zh.epub --provider anthropic --model flash --allow-paid-api
```

## 6. Model registry

### 6.1 Provider identity

`ai/model_profiles.py` widens `ProviderName` to `cli | api | openai | anthropic` and exposes one predicate, `is_metered(provider)`, true for every value except `cli`. Application code uses that predicate instead of comparing with `"api"`.

### 6.2 Pinned mappings

Each metered vendor gets a `(profile) -> MeteredModel` table:

```python
@dataclass(frozen=True)
class MeteredModel:
    model_id: str
    max_output_tokens: int   # the cap BookWeaver requests, at or below the vendor limit
    reasoning: str | None    # lowest supported reasoning setting, or None if the model has none
```

- `flash` maps to the vendor's fast or economical tier, `pro` to its high-quality tier.
- The implementation PR fills the concrete IDs and limits from the vendor's current documentation and records the source and date beside the table. Neither this spec nor code comments may infer them from memory.
- Reasoning models count reasoning tokens against output and cost. The transport requests the lowest reasoning level the pinned model accepts. Anthropic extended thinking stays off.
- `ResolvedModel` gains `max_output_tokens: int | None` and `reasoning: str | None`. Both are `None` for `cli`.

## 7. Architecture

### 7.1 Transport port

A new port module, `ai/ports/metered.py`, defines the vendor boundary. It has no dependency on the application or the model registry:

```python
@dataclass(frozen=True)
class TransportReply:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None   # None when the vendor does not report it
    truncated: bool                   # vendor reported the output cap as the stop reason

class IMeteredTransport(Protocol):
    backend: str                      # "gemini_api" | "openai_api" | "anthropic_api"
    def send(self, *, model_id: str, system: str, user: str,
             max_output_tokens: int, reasoning: str | None,
             timeout_seconds: float) -> TransportReply: ...
```

Transports live in `ai/adapters/providers/` (`gemini_transport.py`, `openai_transport.py`, `anthropic_transport.py`) and depend only on `ai.ports`, which satisfies the existing `ai.adapters` Tach rule. Each transport:

- imports its SDK lazily inside the constructor;
- disables SDK retries (`max_retries=0` for openai and anthropic; `HttpRetryOptions(attempts=1)` for google-genai);
- maps vendor stop reasons to `truncated`: OpenAI `finish_reason == "length"`, Anthropic `stop_reason == "max_tokens"`, Gemini `finish_reason == MAX_TOKENS`;
- maps vendor exceptions to the existing port errors (§8);
- never logs or raises with request or response text.

Vendor specifics:

- **OpenAI**: The implementation PR chooses Chat Completions or Responses, whichever exposes `max_output_tokens`, reasoning control, stop reason, and cached-token usage for the pinned models. OpenAI applies prompt caching automatically. The transport reports `cached_tokens` when present.
- **Anthropic**: Messages API with streaming. The SDK rejects long non-streaming requests, and a whole batch can run for minutes. `max_tokens` is always explicit. The system prompt is sent as one text block with `cache_control: {"type": "ephemeral"}`. Usage comes from the final message, including `cache_read_input_tokens`. A prompt below the vendor's minimum cacheable length simply reports no cache hits.
- **Gemini**: The current `_PaidProvider` request moved behind the port. Behavior is unchanged, except that it now detects truncation.

### 7.2 Metered provider shell

`ai/runtime_factory.py` replaces the Gemini-specific `_PaidProvider` with one `MeteredProvider(ITranslationProvider)` that wraps any `IMeteredTransport`. It:

1. frames the batch with the existing `_delimiter` helpers (`augment_prompt_for_batch` into `system`, `join_segments` into `user`);
2. appends a pending `RequestUsage`, persists the audit, calls `send` once, and records the outcome. This is today's sequence, generalized;
3. raises `OutputTruncatedError` when `reply.truncated`, even if the text happens to split;
4. raises `ProviderUnavailableError` on empty text;
5. otherwise returns `split_response(...)`.

`MeteredProvider` exposes `backend` from its transport and `runtime_version = None`.

### 7.3 Factory and authorization

`DefaultProviderFactory.create` branches once on `is_metered`:

- Authorization keeps the SPEC-020 rules: one consent per invocation, covering glossary extraction and translation. The interactive message names the vendor and the concrete model, for example `Metered Anthropic API: <model_id>; remaining source approximately N characters ...`. Non-interactive runs require `--allow-paid-api`.
- API key lookup: environment variable first, then configuration. The variables are `GEMINI_API_KEY`, `OPENAI_API_KEY`, and `ANTHROPIC_API_KEY`. A missing key fails before any request and names both sources.
- `usage_snapshot()` reports whenever the runtime provider is metered, not only `api`.

### 7.4 Orchestration changes (new application path only)

- Replace `model.provider == "api"` with `is_metered(model.provider)` for split depth and usage snapshots.
- Take the segment `backend` from the active provider's `backend` attribute instead of `"antigravity" if cli else "gemini_api"`. `ITranslationProvider` gains `backend: str | None = None`, mirroring `runtime_version`. `AntigravityProvider` sets `"antigravity"`.
- Use metered batch defaults (§9) when `is_metered`.

## 8. Failure policy

SPEC-020 §7 applies unchanged to every metered provider. Mapping:

| Vendor condition | Port error | Engine action |
|---|---|---|
| 401 / 403, invalid key | `ProviderAuthenticationError` | stop, checkpoint preserved |
| 429, rate or credit exhausted | `RateLimitError` | stop |
| timeout, connection error, 5xx, overloaded | `ProviderUnavailableError` | stop |
| stop reason = output cap | `OutputTruncatedError` (new, subclass of `ProviderUnavailableError`) | stop; message advises a smaller `--max-batch-chars` |
| wrong segment count / malformed tags | `TranslationError` | stop (metered split depth stays 0) |
| refusal or empty output | `ProviderUnavailableError` | stop |

`OutputTruncatedError` is not split-eligible. That keeps "no automatic additional paid request" intact. Small metered batch defaults make truncation the exception. §13 Q3 asks whether the owner wants a bounded split on truncation instead.

## 9. Batch defaults

- New configuration keys `epub_resilience.metered_max_batch_chars` and `epub_resilience.metered_max_batch_segments` apply when the provider is metered. CLI `--max-batch-chars` / `--max-batch-segments` still override.
- The starting defaults are **8,000 characters and 40 segments**. They are deliberately conservative: an 8,000-character English batch yields roughly 3k–5k output tokens of Chinese, well inside any plausible pinned `max_output_tokens`. Phase 3 calibrates them with authorized evidence before they are called final.
- Startup validation: when `max_batch_chars` multiplied by a fixed conservative output-tokens-per-source-character factor exceeds the pinned `max_output_tokens`, fail before any request, with a message naming both numbers. The implementation records the factor and its derivation in code.
- Checkpoint consequence (no schema change): `max_batch_chars` is a force-resume-overridable identity field (SPEC-020 §9.2). Moving a book between `cli` and a metered provider therefore requires `--force-resume`, or an explicit `--max-batch-chars` equal to the checkpoint's value. This is intentional and must appear in the mismatch message.

## 10. Configuration and persistence

### 10.1 Schema (`ai/config_schema.json`)

```json
"openai_api":    { "api_key": "string|null", "timeout_seconds": "number > 0, <= 86400", "max_output_tokens": "integer >= 1" },
"anthropic_api": { "api_key": "string|null", "timeout_seconds": "number > 0, <= 86400", "max_output_tokens": "integer >= 1" }
```

- `additionalProperties: false` throughout, and unknown keys still fail loudly.
- `max_output_tokens` may only lower the pinned value. A higher value is rejected.
- `gemini_api` gains the same two optional keys for parity.
- Configuration can never authorize paid execution. User configuration is never rewritten.
- `config/config.json.example` documents the new sections, using environment-variable keys only.

### 10.2 Checkpoint provenance (`ai/checkpoint_store.py`)

- Accepted `provider` values become `cli | api | openai | anthropic | legacy_unknown`.
- Accepted `backend` values gain `openai_api | anthropic_api`.
- `CheckpointIdentity` is unchanged. SPEC-020 §9.2 keeps provider and concrete model audit-only. Mixed-vendor continuation is reported by the existing "Mixed-model continuation" notice.
- Without the provenance change, a metered run would write a checkpoint that fails to load on resume (`Invalid checkpoint provenance`). Phase 2 must land this together with the transports.

### 10.3 Audit (`.bookweaver_runs/<run_id>.json`)

- `RequestUsage` gains `cached_input_tokens: int | None` and `backend: str`.
- `usage_scope` becomes `"metered_api_requests"`. Readers of older audit files keep working because the field is informational.
- The audit never stores keys, prompts, or responses.

## 11. Phases

**Phase 1: Shell and Gemini parity (no user-visible change)**
Add `ai/ports/metered.py`, `MeteredProvider`, and the Gemini transport. Delete `_PaidProvider`. All existing runtime-factory, invocation-audit, and application tests pass unchanged, except the new truncation test.

**Phase 2: OpenAI and Anthropic**
Add the two transports, registry entries with cited limits, CLI values, configuration schema, factory branches, checkpoint provenance values, `backend` reporting, metered batch defaults, and dependency declarations. Add `openai` and `anthropic` to `[project].dependencies` next to `google-genai`, with lazy imports. Update Tach for the new port module.

**Phase 3: Authorized calibration (requires separate owner authorization)**
Run one short probe chapter per vendor and profile. Record cost, cached tokens, output/source ratio, and wall time in `docs/plans/`, separate from mocked tests. Adjust §9 defaults from that evidence. The probe is a calibration check, not book acceptance.

**Phase 4 (optional): OpenAI-shape `base_url`**
Add `openai_api.base_url`. A non-default base URL requires an explicit `openai_api.models: {flash, pro}` mapping with `max_output_tokens`, because the official registry does not describe other hosts. Authorization stays mandatory, since BookWeaver cannot know whether the host bills. Audit records the host name only.

## 12. Acceptance criteria

Offline (mocked SDK clients at the transport boundary; no network):

- [ ] Each metered provider refuses to construct without `--allow-paid-api` when non-interactive, and configuration cannot authorize.
- [ ] `--allow-paid-api` with `--provider cli` and `--effort` with a metered provider fail before any provider construction.
- [ ] Exactly one SDK call per planned batch. SDK retry is disabled; the test asserts `max_retries=0` or the equivalent.
- [ ] A vendor truncation stop reason raises `OutputTruncatedError`, persists the audit as failed, and leaves prior checkpoint batches intact.
- [ ] Each vendor error class maps per §8.
- [ ] Anthropic requests carry an explicit `max_tokens`, use streaming, and mark the system block with `cache_control`.
- [ ] Usage, including cached tokens, reaches the audit file and the checkpoint usage summary. Unknown usage stays `None`, never `0`.
- [ ] A checkpoint written by an `openai` or `anthropic` run reloads on resume with correct `provider`, `backend`, and `model`.
- [ ] Switching between `cli` and a metered provider on one checkpoint fails without `--force-resume` and names `max_batch_chars`.
- [ ] Metered batch defaults apply only to metered providers. CLI flags override them.
- [ ] Unknown keys under `openai_api` and `anthropic_api` are rejected. A `max_output_tokens` above the pinned value is rejected.
- [ ] A glossary extraction plus translation run asks for authorization once.
- [ ] Gemini behavior matches the pre-change tests.
- [ ] `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`, and `uv run tach check` pass.

Evidence (Phase 3, authorized separately):

- [ ] One probe per vendor completes with sane segment alignment, recorded cost, and cache-hit evidence.

## 13. Open decisions for the owner

1. **Provider naming.** Keep `api` for Gemini (recommended; existing checkpoints record `provider: api`) or add a `gemini` alias as well?
2. **Profile mapping.** Which tier each vendor's `flash` and `pro` should mean. The recommendation is economical/fast for `flash` and the top general model for `pro`; concrete IDs are filled from vendor docs in Phase 2.
3. **Truncation recovery.** Stop (recommended, no extra paid request) or allow one bounded split of the truncated batch under the same authorization?
4. **Batch defaults.** Accept 8,000 characters / 40 segments as the starting point until Phase 3 calibration?
5. **Phase 4.** Include `base_url` support at all?
6. **Async batch APIs.** Write the follow-up spec for Anthropic Message Batches and OpenAI Batch (about half price, higher latency) after Phase 2?

## 14. Risks

| Risk | Mitigation |
|---|---|
| Output cap truncates a batch | Small metered defaults, a startup bound check, explicit truncation error |
| Reasoning tokens inflate cost and consume the output cap | Pin the lowest reasoning level per model; record output tokens per request |
| Vendor model IDs or limits drift | One registry table with cited source and date; a failure on unknown model is loud, never a silent substitute |
| Smaller batches weaken cross-paragraph consistency | Glossary stays in the system prompt; Phase 3 compares quality against the Antigravity baseline on the same chapter |
| Repeated system prompt raises cost | Anthropic explicit cache control; OpenAI automatic prefix caching; cached tokens audited |
| Spend surprises | Per-invocation authorization with remaining-character estimate, per-request audit persisted even on failure |

## 15. Status history

- 2026-11-07: Draft written from codebase analysis and open-source survey; awaiting owner review.
