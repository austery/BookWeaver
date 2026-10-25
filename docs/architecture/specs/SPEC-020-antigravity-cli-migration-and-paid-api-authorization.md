---
specId: SPEC-020
title: Antigravity CLI Migration and Paid API Authorization
status: 📝 草案 (Draft)
priority: P1 - Core Feature
creationDate: 2026-07-16
lastUpdateDate: 2026-07-17
owner: User (AI-Assisted)
relatedSpecs:
  - SPEC-011-model-selection-and-config-abstraction
  - SPEC-012-core-translation-engine-hexagonal
  - SPEC-016-batch-sanity-probe
  - SPEC-017-epub-div-extraction-and-cross-doc-batching
tags:
  - antigravity-cli
  - gemini-api
  - paid-api-authorization
  - provider-migration
  - model-profiles
  - checkpoint-resume
  - epub-translation
---

# SPEC-020: Antigravity CLI Migration and Paid API Authorization

## 1. Goal

Replace the discontinued Gemini CLI translation runtime with Antigravity CLI while preserving EPUB resume safety and requiring explicit, informed user authorization before any metered Gemini API token usage.

## 2. Review Gate

This document records the design approved by the owner on 2026-07-16. External review v1 completed on 2026-07-17, and the owner approved its findings for incorporation into this revision.

This revision remains a draft pending owner review of the amended contract. No implementation plan or runtime change may begin until the owner explicitly promotes this SPEC to `🟡 待实施 (Ready for Implementation)`.

## 3. Background

### 3.1 Current Runtime

BookWeaver is an EPUB-first translation application with a hexagonal translation core. `TranslationEngine` depends on `ITranslationProvider`, while the composition root in `ai/cli.py` selects concrete provider adapters.

The current CLI path is Gemini-specific:

- `GeminiProvider` runs `gemini --model <model> -p`.
- `GeminiCLIAdapter` wraps the raw provider with batch framing, response parsing, and retry behavior.
- `ModelProbe` invokes Gemini CLI directly.
- `ProviderFactory` creates Gemini CLI or Gemini API implementations.
- `00_extract_glossary.py` bypasses the main composition root and constructs Gemini providers directly.
- `--cli-api-fallback` and `--fallback-provider api` can automatically move work from a subscription CLI to the metered Gemini API.

Gemini CLI no longer serves the owner's translation workflow. Antigravity CLI is the replacement subscription runtime.

### 3.2 Verified Antigravity Command Contract

The local Antigravity CLI inspected on 2026-07-16 was `agy 1.1.3`. It exposes command-level model selection, non-interactive print mode, a print timeout, and a model-list command.

The provider command contract is:

```bash
agy \
  --model "Gemini 3.5 Flash (Low)" \
  --print "<wrapper prompt>" \
  --print-timeout 600s
```

The PureSubs reference implementation establishes several transport facts that BookWeaver must preserve:

- unknown `--model` values may silently fall back instead of failing;
- authentication and response-timeout messages may appear with exit code `0`;
- long prompts should be written to a temporary file and referenced by a short wrapper prompt;
- an outer process timeout is still required in addition to `--print-timeout`;
- every success, failure, and timeout path must clean up temporary prompt files;
- stdout must contain usable content rather than a local artifact link.

### 3.3 Billing Boundary

Antigravity CLI and Gemini API have different economic contracts:

| Runtime | Capacity model | Default governance |
|---|---|---|
| Antigravity CLI | Existing subscription quota | Primary translation runtime; no per-token API charge |
| Gemini API | Metered token usage | User-authorized execution only |

Technical availability is not authorization to spend money. A CLI failure must never trigger Gemini API usage automatically.

### 3.4 Existing Checkpoint Contract

EPUB translation already persists completed segment translations after each successful batch. Resume is more granular than chapter-level recovery:

- every translated segment has a stable EPUB-derived ID;
- a completed batch is sanity-checked before persistence;
- checkpoint writes use temporary files followed by atomic replacement;
- resumed segments are skipped before new batches are planned;
- the failed batch is not persisted, while all earlier successful batches remain reusable.

The current schema stores concrete `provider` and `model` values as soft compatibility keys. Cross-provider resume is possible only through the coarse `--force-resume` override, which simultaneously accepts unrelated prompt, language, model, and batch-setting mismatches. The schema cannot express the narrower intent that an Antigravity `flash` checkpoint may resume through Gemini API `flash` while all other compatibility constraints remain enforced.

## 4. Design Decision

**Chosen approach**: Keep BookWeaver's public `cli|api` provider contract, replace the internal `cli` backend with Antigravity, expose only `flash|pro` logical model profiles, remove automatic paid fallback, require per-invocation Gemini API authorization, and upgrade checkpoints to resume across providers within the same logical profile.

**Rationale**: This preserves normal user commands and the hexagonal core while isolating Antigravity's distinct process semantics. It also makes the billing boundary enforceable: subscription failure stops safely, and paid execution begins only after a separate user decision.

| Alternative | Pros | Cons | Decision |
|---|---|---|---|
| Rename the public provider to `antigravity` | Explicit backend identity | Unnecessary breaking CLI change; couples the user contract to one executable | Rejected |
| Replace the Gemini executable name in `GeminiProvider` | Small diff | Preserves incorrect Gemini error, model, timeout, and billing semantics | Rejected |
| Automatically switch to Gemini API after CLI failure | Maximizes unattended completion | Can create an unbounded cost spike without informed consent | Rejected |
| Map `lite` to Antigravity Flash Low | Preserves an old alias | Creates false model identity and misleading checkpoints | Rejected |
| Accept arbitrary Antigravity model strings | Flexible | Unsafe because invalid strings can silently fall back | Rejected |
| Antigravity primary plus separately authorized Gemini API mode | Preserves subscription-first behavior, cost control, and resumability | Requires an explicit resume step after CLI failure | Chosen |

## 5. Public CLI Contract

### 5.1 Provider Selection

The existing provider names remain stable:

```text
--provider cli    Antigravity CLI; default
--provider api    Gemini API; metered and authorization-gated
```

The normal command remains:

```bash
uv run bookweaver book.epub \
  --output translated.epub \
  --model flash
```

Direct paid execution is explicit:

```bash
uv run bookweaver book.epub \
  --output translated.epub \
  --model flash \
  --provider api
```

### 5.2 Model Profiles

The public `--model` value is a logical profile, not a provider-specific model string.

| Profile | Antigravity model | Gemini API model | Default use |
|---|---|---|---|
| `flash` | `Gemini 3.5 Flash (Low)` | `gemini-2.5-flash` | Default translation and normal glossary work |
| `pro` | `Gemini 3.1 Pro (Low)` | `gemini-2.5-pro` | Complex translation and high-value glossary extraction |

The default changes from the concrete Gemini identifier `gemini-2.5-flash` to the logical profile `flash`.

A logical profile represents the same intended quality and workload tier, not model identity or generation equivalence. Antigravity and Gemini API currently map each profile to different model generations. Cross-provider resume therefore preserves completed work at the possible cost of visible differences in voice, register, or terminology; Sections 8 and 9 make that tradeoff explicit and auditable.

`lite`, `gemini-2.5-flash-lite`, arbitrary Antigravity display names, and arbitrary Gemini API model IDs are rejected at argument or model-resolution time. The error must identify the allowed values: `flash` and `pro`.

### 5.3 Removed Automatic Fallback Flags

The following flags are removed because their semantics authorize paid execution implicitly:

- `--cli-api-fallback`
- `--fallback-provider api`

They must not be ignored or reinterpreted. They fail with a migration message:

```text
Automatic paid API fallback has been removed.
Resume explicitly with --provider api after reviewing the paid API authorization prompt.
```

## 6. Provider Architecture

### 6.1 Stable Core Boundary

`ITranslationProvider` and `TranslationEngine` remain provider-agnostic. The core engine must not know about `agy`, Gemini API credentials, billing prompts, subprocess output, or provider-specific model names.

### 6.2 Model Profile Registry

A typed model-profile registry owns provider-specific identity:

```text
LogicalModelProfile
├── name: flash | pro
├── antigravity_model: verified display name
├── gemini_api_model: concrete API identifier
└── tier: standard | pro
```

One resolved profile is passed to the provider factory. The factory selects only the model field belonging to the requested provider.

Concrete provider strings are provenance. The logical profile is the compatibility contract.

The registry replaces `ModelResolver`, `ModelRole`, and config-defined aliases. It never accepts an arbitrary provider model string and does not own provider fallback or availability probing.

### 6.3 Legacy Model Configuration Migration

Legacy configuration must never be silently ignored or allowed to weaken the static `flash|pro` allowlist.

| Existing key | v2 disposition |
|---|---|
| `default_model` | Retained, but its value must be `flash` or `pro` |
| `model_thresholds.*.model` | Retained, but every value must be `flash` or `pro`; `lite` is invalid |
| `terminology_extraction.extraction_model` | Retained, but its value must be `flash` or `pro` |
| `model_aliases` | Removed; fail with migration guidance |
| `fallback_chain` | Removed; fail with migration guidance |
| `enable_fallback` | Removed; fail with migration guidance |
| `model_probe` | Removed; Antigravity availability is checked through `agy models` |
| `gemini_api.model` | Removed; the profile registry owns the API model mapping |
| `epub_resilience.cli_api_fallback_enabled` | Removed; fail with paid-fallback migration guidance |

Configuration validation occurs before provider construction. A removed key, concrete provider model, or `lite` value produces an actionable error naming the accepted profile values and the replacement configuration. The ignored local `config/config.json` remains user-owned and is never rewritten automatically.

### 6.4 Antigravity Raw Provider

The raw Antigravity provider owns process-level behavior:

1. Validate the logical profile against BookWeaver's static allowlist.
2. Run `agy models` once per BookWeaver invocation and require the mapped display name to be present.
3. Write the full prompt to a uniquely named temporary file.
4. Build a short wrapper prompt instructing Antigravity to read that file and return the final translation in stdout.
5. Spawn `agy` with an argument array; never build a shell command string.
6. Pass `--model`, `--print`, and `--print-timeout` explicitly.
7. Enforce an outer hard timeout and terminate a hung process.
8. Parse stdout, stderr, and exit code together.
9. Delete the temporary prompt file on every settlement path.

The per-run `agy models` check supplements rather than replaces the static allowlist. The allowlist prevents arbitrary input; the live check prevents a formerly valid display name from silently falling back after Antigravity renames or removes a model.

If model discovery fails or the selected display name is absent, BookWeaver stops before translation. It does not use the current Antigravity session model and does not switch to Gemini API.

### 6.5 Antigravity CLI Adapter

`AntigravityCLIAdapter` implements `ITranslationProvider` and owns translation protocol behavior:

- delimiter or tagged-segment framing;
- batch prompt augmentation;
- response splitting and segment-count enforcement;
- mapping raw Antigravity failures to typed provider errors.

The existing delimiter/tag helpers remain shared with the Gemini API adapter.

### 6.6 Composition Root

`ProviderFactory` and `ai/cli.py` become the only runtime construction boundary for both main translation and glossary extraction.

`00_extract_glossary.py` must stop instantiating provider classes directly. It resolves the same logical profile and uses the same factory, Antigravity checks, and paid authorization policy as the main command.

## 7. Failure and Retry Policy

### 7.1 Typed Outcome Classes

Provider failures must remain distinguishable:

| Outcome | Examples | Runtime action |
|---|---|---|
| Configuration error | unsupported profile, missing API key | Stop before provider invocation |
| Authentication error | Antigravity login required or expired | Persist prior batches and stop |
| Provider unavailable | missing binary, spawn failure, connection failure | Persist prior batches and stop |
| Timeout | Antigravity response timeout or outer hard timeout | Kill if needed, persist prior batches, and stop |
| Capacity error | recognized quota or rate-limit exhaustion | Persist prior batches and stop |
| Output transport error | empty stdout or local artifact link | Persist prior batches and stop |
| Protocol error | missing delimiter, wrong segment count | Antigravity may use bounded split-retry; Gemini API stops after the failed request |
| Quality error | sanity-probe empty, ratio, or target-language failure | Do not persist the failed batch; stop |

Infrastructure, authentication, timeout, capacity, output-transport, and paid-provider protocol errors are not eligible for recursive split-retry. Antigravity protocol errors may remain eligible when splitting can safely recover a malformed multi-segment response.

### 7.2 Retry Budgets

No provider adapter may own an unbounded retry loop. The composition root injects a provider-appropriate engine retry policy; `TranslationEngine` applies that policy without inspecting provider names.

- Antigravity process execution has one attempt per engine provider call.
- Antigravity may retain bounded split behavior only for eligible protocol or batch-capability failures.
- Gemini API performs exactly one network request attempt for each planned batch: the Google GenAI SDK retry option is explicitly set to one attempt, the raw provider loop is set to one attempt, and the engine split depth is zero.
- A failed paid request, including timeout, rate-limit, server, empty-output, or protocol failure, produces no retry or split request. It stops the run and preserves the checkpoint.
- Another paid attempt requires a new process invocation and new authorization.
- Whole-provider fallback and provider-chain retry do not exist in BookWeaver.

This policy protects both subscription capacity and paid API spend from retry multiplication.

### 7.3 CLI Failure UX

When Antigravity fails, BookWeaver prints:

- the typed failure class and concise detail;
- the checkpoint path;
- restored and newly completed segment counts;
- the first pending segment or document identity;
- a suggested paid resume command.

The suggested command is informational only and is never executed automatically.

## 8. Paid Gemini API Authorization

### 8.1 Interactive Authorization

Before the first Gemini API request, an interactive invocation displays a blocking authorization prompt:

```text
PAID API AUTHORIZATION REQUIRED

Provider: Gemini API
Model: gemini-2.5-flash
Remaining segments: 1,284
Estimated source tokens: 286,000

Checkpoint models: Gemini 3.5 Flash (Low) — 416 completed segments
Resume model: gemini-2.5-flash
Warning: continuing with a different model generation may change translation voice or terminology.

This execution consumes metered Gemini API tokens and may incur charges.
Type USE_API to continue:
```

Only the exact confirmation `USE_API` authorizes the invocation. Any other input stops without making an API request.

The token figure is an estimate derived from the remaining source content. It is an awareness guard, not a billing quote. BookWeaver must not hard-code a dollar price that can drift independently of Google's pricing.

### 8.2 Non-Interactive Authorization

Non-interactive execution requires an explicit command-line capability:

```bash
--allow-paid-api
```

Rules:

- `--provider api` without a TTY and without `--allow-paid-api` fails before provider construction.
- `--allow-paid-api` is invalid unless `--provider api` is selected.
- configuration files and environment variables cannot grant paid authorization.
- authorization applies only to the current process invocation.
- checkpoint state records that API work occurred but never stores reusable authorization.

### 8.3 Authorized Resume

After Antigravity failure, the user may resume explicitly:

```bash
uv run bookweaver book.epub \
  --output translated.epub \
  --model flash \
  --provider api \
  --resume
```

The interactive prompt still appears. For a reviewed non-interactive run, the user adds `--allow-paid-api`.

When restored segments were produced by a different concrete model, BookWeaver prints the existing model or models, restored segment counts, the newly selected model, and the mixed-generation quality warning before authorization. The warning does not invalidate the checkpoint or add a second confirmation token: accepting `USE_API`, or supplying `--allow-paid-api` non-interactively, explicitly accepts both metered execution and the documented continuity tradeoff for that invocation.

## 9. Checkpoint Schema v2

### 9.1 Persistence Granularity

Checkpointing remains successful-batch and segment-level, not chapter-transaction-level.

This is intentionally more precise than chapter recovery. If five chapters and half of chapter six have passed sanity checks and been persisted, all of those segments are reused. Only the failed or unstarted batch is retried.

Cross-document batching remains compatible because each segment retains a stable ID and document path.

### 9.2 Compatibility Tiers

Checkpoint reuse uses three explicit tiers:

| Tier | Fields | Resume behavior |
|---|---|---|
| Absolute-hard | input file signature, input format, EPUB segmenter signature | Any mismatch invalidates the checkpoint and cannot be overridden by `--force-resume` |
| Force-resume-overridable | target language, logical model profile, effective system-prompt hash including glossary content, batch protocol version, maximum batch characters, separator overhead | Any mismatch rejects normal resume; `--force-resume` may accept the documented quality or protocol risk |
| Audit-only | public provider, concrete backend, concrete provider model, completion timestamp, paid API request and token metadata | Recorded for visibility; never invalidates an otherwise compatible resume |

This preserves the schema-v1 distinction between absolute-hard and force-resume-overridable fields. The intentional behavior change is narrower: concrete `provider` and `model` values stop gating resume when the v2 logical profile matches, so a same-profile provider transition does not require the coarse `--force-resume` override.

### 9.3 Segment Provenance

Schema v2 preserves the existing two-file checkpoint layout. `state.json` owns compatibility keys and run-level audit summaries:

```json
{
  "schema_version": 2,
  "input_signature": "sha256:...",
  "input_format": "epub",
  "segmenter_signature": "epub-div-v1",
  "output_lang": "zh",
  "logical_model_profile": "flash",
  "system_prompt_hash": "sha256:...",
  "batch_protocol_version": "segment-tags-v1",
  "max_batch_chars": 60000,
  "separator_overhead": 6,
  "translated_segment_count": 420,
  "providers_used": ["cli", "api"],
  "backends_used": ["antigravity", "gemini_api"],
  "models_used": ["Gemini 3.5 Flash (Low)", "gemini-2.5-flash"],
  "paid_api_usage": {
    "request_count": 1,
    "input_tokens": 12450,
    "output_tokens": 8192
  }
}
```

`translations.json` owns the translated text and actual per-segment provenance:

```json
{
  "schema_version": 2,
  "segments": {
    "EPUB/chapter01.xhtml::0": {
      "translated": "Translated text",
      "logical_model_profile": "flash",
      "provider": "cli",
      "backend": "antigravity",
      "model": "Gemini 3.5 Flash (Low)",
      "completed_at": "2026-07-16T12:00:00Z"
    },
    "EPUB/chapter06.xhtml::4": {
      "translated": "Translated text",
      "logical_model_profile": "flash",
      "provider": "api",
      "backend": "gemini_api",
      "model": "gemini-2.5-flash",
      "completed_at": "2026-07-16T14:00:00Z"
    }
  }
}
```

Under mixed-provider resume, no single run-level provider or concrete model represents the whole checkpoint. The `state.json` arrays and paid usage fields are derived audit summaries, while `translations.json` is authoritative for the provenance of each completed segment. Compatibility checks read only the tiered compatibility fields from `state.json`; audit summaries and segment provenance cannot grant authorization or invalidate reuse.

### 9.4 Schema v1 Migration

| v1 model | v2 logical profile | Resume behavior |
|---|---|---|
| `gemini-2.5-flash` | `flash` | Reuse automatically when absolute-hard and force-resume-overridable keys match |
| `gemini-2.5-pro` | `pro` | Reuse automatically when absolute-hard and force-resume-overridable keys match |
| `gemini-2.5-flash-lite` | none | Require `--model flash --force-resume`; never remap silently |
| Unknown model | none | Reject unless the owner explicitly force-resumes |

Legacy segment strings are imported with the v1 state-level provider and model as provenance. If provenance is incomplete, the backend is recorded as `legacy_unknown`, not guessed.

Schema-v1 fields are migrated without inventing unavailable metadata: the concrete v1 model maps to the logical profile through the table above, the existing `system_prompt_hash` remains the hash of the complete effective prompt including any injected glossary, and the batch protocol version is inferred from the versioned v1 EPUB adapter contract. If that protocol cannot be identified unambiguously, it is a force-resume-overridable mismatch rather than an assumed match.

Reading v1 does not overwrite it immediately. The next successfully sanity-checked batch writes the complete state atomically as schema v2.

`--force-resume` can override target-language, profile, prompt/glossary, protocol, or batch-setting differences, but it cannot override input signature, input format, or segmenter-signature differences. Provider and concrete-model differences require no override when the logical profile and all other compatibility fields match.

## 10. Removal and Documentation Scope

After the Antigravity path and migration tests pass, remove obsolete Gemini CLI runtime code:

- `ai/gemini_provider.py`;
- `ai/adapters/providers/gemini_cli_adapter.py`;
- `ai/model_resolver.py` and `ai/model_probe.py`, replaced by the typed profile registry and live Antigravity model check;
- Gemini CLI construction in `ai/provider_factory.py`;
- direct provider construction in `00_extract_glossary.py`;
- `_CLIAPIFallbackAdapter` and automatic paid fallback wiring;
- `cli_api_fallback_enabled` wiring in the reference-only `ai/epub_translate_roundtrip.py`, if that module is retained;
- obsolete tests whose only contract is Gemini CLI behavior.

Keep `ai/gemini_api_provider.py` and `GeminiAPIAdapter` as the separately authorized paid provider.

Update:

- `README.md`;
- `CLAUDE.md`;
- `config/config.json.example`;
- `translatebook.sh` help and forwarding;
- provider, model, checkpoint, glossary, and CLI compatibility tests.

The ignored local `config/config.json` is user-owned runtime state and must not be edited or committed.

Historical specs remain unchanged as implementation history. This SPEC supersedes their Gemini CLI runtime assumptions without rewriting completed decisions.

## 11. Implementation Phases

### Phase 1: Contract and Safety Tests

- [ ] Add failing tests for the two logical model profiles and `lite` rejection.
- [ ] Add failing tests proving invalid or unavailable Antigravity models stop before translation.
- [ ] Add failing tests proving every Antigravity failure class makes zero Gemini API calls.
- [ ] Add failing tests proving each Gemini API batch configures the SDK for one network attempt, invokes the raw provider once, and never split-retries after failure.
- [ ] Add failing tests for interactive and non-interactive paid authorization.
- [ ] Add failing tests for same-profile cross-provider checkpoint resume and schema v1 migration.
- [ ] Add failing tests proving removed model/fallback configuration fails before provider construction.

**Acceptance**: Tests encode the approved provider, cost, model, and checkpoint boundaries before production implementation changes.

### Phase 2: Antigravity Provider and Adapter

- [ ] Add the typed model-profile registry.
- [ ] Implement the raw Antigravity subprocess provider.
- [ ] Implement per-run `agy models` verification.
- [ ] Implement the Antigravity batch adapter using existing framing helpers.
- [ ] Inject provider-specific retry policies while keeping `TranslationEngine` provider-agnostic.
- [ ] Map infrastructure failures so the engine cannot split-retry them.
- [ ] Prove temporary-file cleanup across success, spawn failure, parse failure, and hard timeout.

**Acceptance**: Unit tests assert the exact argument array, model enforcement, false-success parsing, timeout behavior, and cleanup contract.

### Phase 3: Composition and Authorization

- [ ] Make `cli` construct Antigravity and keep `api` constructing Gemini API.
- [ ] Add interactive paid authorization and `--allow-paid-api`.
- [ ] Configure Gemini API for one SDK/network attempt, one raw-provider attempt per planned batch, and zero engine split depth.
- [ ] Remove automatic fallback flags and wiring with actionable migration errors.
- [ ] Replace legacy model-resolution configuration with strict profile validation and migration errors.
- [ ] Route standalone glossary extraction through the same composition root.
- [ ] Preserve the existing shell entry point and public `cli|api` provider names.

**Acceptance**: Main translation and glossary extraction cannot reach Gemini API without authorization, and existing non-fallback CLI commands remain compatible.

### Phase 4: Checkpoint Schema v2

- [ ] Implement structured segment provenance and provider usage summaries.
- [ ] Persist the v2 compatibility state and per-segment provenance in separate atomic checkpoint files.
- [ ] Migrate compatible schema v1 `flash` and `pro` checkpoints.
- [ ] Require explicit force-resume for legacy `lite` checkpoints.
- [ ] Allow same-profile Antigravity-to-API resume without retranslation.
- [ ] Preserve atomic persistence after sanity checks.

**Acceptance**: A simulated 20-chapter run can complete five chapters with Antigravity, stop on chapter six, resume with authorized Gemini API, and make zero provider calls for all restored segments.

### Phase 5: Removal, Documentation, and Verification

- [ ] Delete obsolete Gemini CLI production modules and references.
- [ ] Update configuration examples, contributor guidance, and user documentation.
- [ ] Run all lint, formatting, shell, compilation, architecture, and test gates.
- [ ] Run a minimal Antigravity EPUB smoke test.
- [ ] Run no live Gemini API smoke test without a separate owner authorization at execution time.

**Acceptance**: No runtime path invokes `gemini` CLI, all automated gates pass, Antigravity completes the controlled fixture, and paid API smoke remains explicitly gated.

## 12. Acceptance Criteria

- [ ] Default `--provider cli --model flash` resolves to `Gemini 3.5 Flash (Low)` and runs the verified `agy` argument contract.
- [ ] `--model pro` resolves to `Gemini 3.1 Pro (Low)` for Antigravity and `gemini-2.5-pro` for Gemini API.
- [ ] `lite`, arbitrary provider model strings, and missing live Antigravity model entries fail before translation.
- [ ] Authentication, timeout, network, capacity, empty-output, and artifact-output failures never invoke Gemini API.
- [ ] Paid API execution requires `USE_API` interactively or `--allow-paid-api` non-interactively.
- [ ] Each paid API batch configures `HttpRetryOptions(attempts=1)`, invokes the raw provider once, and uses zero engine split depth; a failed request makes no additional request.
- [ ] No configuration file, environment variable, or checkpoint can grant paid authorization.
- [ ] A paid authorization applies to one invocation and is not persisted as reusable consent.
- [ ] Schema v2 resumes same-profile work across Antigravity and Gemini API without retranslating restored segments.
- [ ] A cross-generation resume warning identifies prior concrete models, restored segment counts, and the new concrete model before paid authorization.
- [ ] Schema v1 `flash` and `pro` checkpoints migrate without losing completed translations.
- [ ] A failed batch is absent from the checkpoint; all prior successful batches remain present.
- [ ] Segment provenance identifies the actual provider, backend, and model used.
- [ ] `state.json` owns compatibility fields and audit summaries; `translations.json` owns authoritative per-segment provenance.
- [ ] Main translation and standalone glossary extraction share the same provider and authorization boundary.
- [ ] Removed automatic fallback flags fail with actionable migration guidance.
- [ ] Removed alias, fallback, probe, and concrete-model configuration fails before provider construction with actionable migration guidance.
- [ ] No production code invokes Gemini CLI after migration.
- [ ] `uv run ruff check .` passes.
- [ ] `uv run ruff format --check .` passes.
- [ ] `uv run pytest -q` passes.
- [ ] `bash -n translatebook.sh` passes.
- [ ] Changed Python modules pass `uv run python -m py_compile`.
- [ ] A live Antigravity smoke test passes on a minimal EPUB fixture.
- [ ] No live Gemini API smoke occurs without separate owner authorization.

## 13. Non-Goals

- Supporting Antigravity Medium, High, Claude, Opus, or GPT-OSS models.
- Dynamically exposing every model returned by `agy models`.
- Automatically choosing or switching providers.
- Implementing a persistent paid-API budget service or billing dashboard.
- Hard-coding Google's current dollar pricing.
- Changing EPUB segmentation, cross-document batching, bilingual layout, or output packaging.
- Turning checkpoints into chapter-level transactions.
- Generating the implementation plan before external review is complete.

## 14. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Antigravity renames a model and silently falls back | Static allowlist plus per-run `agy models` verification |
| Exit code `0` hides authentication or timeout failure | Parse stdout and stderr before accepting success |
| A hung `agy` process blocks a book indefinitely | Outer hard timeout and explicit process termination |
| Long prompts exceed command-line limits | Temporary prompt file and short wrapper prompt |
| Prompt files leak source book content | Unique names, restrictive temporary location, cleanup on every path |
| Infrastructure errors trigger recursive split retries | Typed non-splittable provider failures |
| Gemini API costs spike after CLI failure or hidden retries | No automatic fallback; per-invocation authorization; SDK, provider, and engine retry layers all constrained to one network attempt and zero split-retry |
| Resume discards already translated chapters after provider change | Logical-profile checkpoint compatibility and schema v2 provenance |
| Different model generations create inconsistent voice or terminology within one book | Pre-authorization mixed-generation warning plus per-segment concrete-model provenance |
| Old `lite` checkpoints are silently reinterpreted | Explicit force-resume requirement |
| Pricing changes make warnings inaccurate | Show estimated tokens, not a hard-coded dollar quote |

## 15. Status History

| Date | Status | Note |
|---|---|---|
| 2026-07-16 | 📝 草案 (Draft) | Owner-approved design recorded; awaiting external AI review before implementation planning |
| 2026-07-17 | 📝 草案 (Draft) | External review v1 findings incorporated; awaiting owner approval of the amended contract |

## 16. Related

- **Code**:
  - `ai/ports/provider.py` — provider port and typed translation errors
  - `ai/core/engine.py` — batching, split policy, resume, and provider invocation
  - `ai/cli.py` — composition root, CLI, sanity probe, and checkpoint persistence
  - `ai/provider_factory.py` — current provider construction
  - `ai/model_resolver.py` — current Gemini-specific model aliases
  - `ai/model_probe.py` — current Gemini CLI probe
  - `ai/gemini_provider.py` — obsolete Gemini CLI transport
  - `ai/gemini_api_provider.py` — retained metered API transport
  - `ai/adapters/providers/gemini_cli_adapter.py` — obsolete CLI adapter
  - `ai/adapters/providers/gemini_api_adapter.py` — retained API adapter
  - `00_extract_glossary.py` — standalone provider-construction bypass to remove
  - `translatebook.sh` — legacy shell entry point and flag forwarding
- **Review**:
  - `pr-reviews/SPEC-020-review-v1.md` — external design review incorporated on 2026-07-17
- **Specs**:
  - [SPEC-011](./SPEC-011-model-selection-and-config-abstraction.md)
  - [SPEC-012](./SPEC-012-core-translation-engine-hexagonal.md)
  - [SPEC-016](./SPEC-016-batch-sanity-probe.md)
  - [SPEC-017](./SPEC-017-epub-div-extraction-and-cross-doc-batching.md)
- **Reference implementation**:
  - `/Users/leipeng/Documents/Projects/puresubs/packages/automation-engine-ytdlp/src/ai/providers/AntigravityCLIProvider.ts`
  - `/Users/leipeng/Documents/Projects/puresubs/packages/automation-engine-ytdlp/src/ai/antigravityModelSelection.ts`
  - `/Users/leipeng/Documents/Projects/puresubs/docs/architecture/specs/SPEC-166-antigravity-command-model-selection.md`
  - `/Users/leipeng/Documents/Projects/puresubs/docs/architecture/specs/SPEC-175-pipeline-complexity-topology-and-evolution-map.md`
