# Design Review — SPEC-020: Antigravity CLI Migration and Paid API Authorization

**Artifact:** `docs/architecture/specs/SPEC-020-antigravity-cli-migration-and-paid-api-authorization.md` (commit `664c0b4`, 552 lines)
**Status under review:** 📝 草案 (Draft) — awaiting external AI review before promotion to `🟡 待实施 (Ready for Implementation)`
**Reviewer role:** Principal engineer (Python / hexagonal translation core)
**Review type:** Specification / design gate review (no code change proposed by the artifact itself)

---

## Summary

SPEC-020 is a well-structured, safety-conscious migration design. Its central guarantee — *technical availability is not authorization to spend money; a CLI failure must never trigger paid API usage automatically* — is sound and its architectural instinct (keep the `cli|api` public contract, swap the internal backend, isolate Antigravity process semantics behind the port) is correct and matches the existing hexagonal layout.

However, two issues must be resolved before this SPEC is promoted to *Ready for Implementation*: the paid-API cost-safety guarantee in §7.2 is **not enforceable by the architecture as described** (the engine's split-retry multiplies paid requests), and the checkpoint compatibility model (§9.2/§9.4) is **internally inconsistent and silently changes today's resume behavior**, which is the very foundation of the schema-v2 migration.

### Findings

| # | Severity | Section | Finding |
|---|----------|---------|---------|
| 1 | **BLOCKER** | §7.1 / §7.2 | Paid API path still multiplies requests through `TranslationEngine` split-retry, contradicting "one request attempt per batch" / "protect paid API spend from retry multiplication". |
| 2 | **BLOCKER** | §3.4 / §9.2 / §9.4 | Checkpoint compatibility-key model is internally inconsistent (flat list vs. force-resume tiers) and silently changes the current soft-key resume contract. |
| 3 | IMPROVEMENT | §5.2 / §9 | `flash`/`pro` profiles span two model generations (Antigravity 3.5/3.1 vs. API 2.5); mixing generations within one book is an unacknowledged translation-quality tradeoff. |
| 4 | IMPROVEMENT | §6.2 / §10 / §16 | Disposition of the existing model-resolution subsystem (`ModelResolver`, `ModelProbe`) and its config keys (`model_aliases`, `fallback_chain`, `enable_fallback`, `model_probe`) is undefined. |
| 5 | IMPROVEMENT | §3.4 | Problem statement overstates the current limitation — cross-provider resume is already possible today via `--force-resume`. |
| 6 | IMPROVEMENT | §9.3 | Schema-v2 JSON example does not reflect the real two-file checkpoint layout, and run-level vs. per-segment provenance consistency is unspecified. |

### Review Gate Recommendation: **Request changes**

Do not promote SPEC-020 to `🟡 待实施` until BLOCKER 1 and BLOCKER 2 are resolved in the document. Findings 3–6 should be addressed in the same revision but are clarifications rather than correctness defects.

---

## Findings

### BLOCKER 1 — The paid-API cost guarantee (§7.2) is not enforceable by the described architecture

§7.1 routes *Protocol error (missing delimiter, wrong segment count)* to "the existing bounded split policy where eligible", and §7.2 states that "Gemini API has one request attempt per batch by default" and that the retry policy "protects both subscription capacity and paid API spend from retry multiplication."

These two statements conflict for the `api` backend, because the existing split policy lives in the engine, not the adapter, and the engine wraps whichever adapter it is given:

- `TranslationEngine` is constructed with the provider adapter for the selected backend — for `--provider api` that adapter is `GeminiAPIAdapter` (`ai/cli.py:1014`, `ai/cli.py:1107`; `create_provider` returns `GeminiAPIAdapter` at `ai/cli.py:716-721`).
- On a protocol / segment-count error the API adapter raises `TranslationError` (`ai/adapters/providers/gemini_api_adapter.py:72`; the count/id checks that raise it are in `ai/adapters/providers/_delimiter.py:132-146`).
- `TranslationEngine._translate_with_resilience` catches `TranslationError`, splits the batch in half, and **recursively retries each half** up to `max_split_depth` — default **10** (`ai/core/engine.py:243-251`, default at `ai/core/engine.py:37`).
- Each retried half is a fresh call into `GeminiAPIProvider`, i.e. a new metered request.

So a single authorized API batch that hits a protocol error can fan out into many paid requests — exactly the "retry multiplication" §7.2 claims to prevent. The guarantee "one request attempt per batch by default" is therefore not implementable while the paid adapter sits inside the same split-retry engine path.

**Recommendation:** In §7, specify explicitly that split-retry is **disabled (or hard-capped at depth 0–1) for the `api` backend**, and reconcile §7.1's "protocol → split" with §7.2's "one attempt per batch" for the API provider specifically (e.g. protocol split-retry is a CLI-only affordance; the paid path fails the batch and stops, preserving the checkpoint). Without this, the spec's headline cost-safety promise cannot be honored by the current engine design.

---

### BLOCKER 2 — Checkpoint compatibility-key model (§9.2/§9.4) is internally inconsistent and silently redefines the current resume contract

This SPEC's schema-v2 migration hinges on the compatibility-key model, but the model is presented inconsistently and does not describe the delta from current behavior.

**(a) §9.2 and §9.4 disagree on the number of tiers.** §9.2 gives one flat list of seven "compatibility keys" that "determine whether translations are safe to reuse" (input signature, input format, segmenter signature, target language, logical profile, system-prompt/glossary hash, batch protocol version). But §9.4 says `--force-resume` "can override profile, prompt, or batch-setting differences, but it cannot override input signature, input format, or segmenter-signature differences." That implies **three** tiers — absolute-hard (input/format/segmenter), force-resume-overridable (profile/prompt/batch), and audit-only (§9.2's second list) — yet §9.2 collapses the first two into one undifferentiated bucket. An implementer cannot derive the correct invalidation logic from §9.2 alone.

**(b) The spec silently changes today's behavior.** The current implementation already uses two tiers:

- Hard keys → start fresh: input signature, input format, segmenter signature (`ai/cli.py:371-382`).
- Soft keys → warn and require `--force-resume`: `output_lang`, `model`, `provider`, `max_batch_chars`, `separator_overhead`, `system_prompt_hash` (`ai/cli.py:384-404`).

SPEC-020 moves `target language` and `system-prompt hash` up into "compatibility keys" and moves `model`/`provider` down to audit-only, but never states the resulting contract changes: (1) a target-language or prompt mismatch would change from soft (overridable) to hard, and (2) a model/provider mismatch would **stop requiring `--force-resume`**. These are exactly the resume behaviors Phase 4 must implement, and leaving them implicit invites an incorrect migration.

**Recommendation:** Replace §9.2's flat list with an explicit three-tier table (Absolute-hard / Force-resume-overridable / Audit-only), make §9.4 consistent with it, and add a short "behavior change vs. schema v1" note stating that target-language/prompt become non-audit keys and that model/provider stop gating resume. Cross-reference `ai/cli.py:371-404` so the implementer knows which existing checks change tier.

---

### IMPROVEMENT 3 — `flash`/`pro` profiles span two model generations; mixing them in one book is an unacknowledged quality tradeoff

§5.2 maps `flash` → Antigravity `Gemini 3.5 Flash (Low)` **and** Gemini API `gemini-2.5-flash`, and `pro` → `Gemini 3.1 Pro (Low)` **and** `gemini-2.5-pro`. Within each profile the two backends are **different model generations** (3.5/3.1 vs. 2.5). §9's cross-provider resume deliberately reuses previously translated segments because "the logical translation profile … is unchanged", and §9.3 shows a checkpoint containing both an `antigravity` segment and a `gemini_api` segment in the same book.

For long-form prose, two different model generations generally produce a different translation voice, register, and terminology. A resumed book can therefore interleave 3.5-Flash and 2.5-flash output, which is a real reader-visible quality risk for a book translator — and the SPEC's §14 risk table does not mention it.

**Recommendation:** Either explicitly accept mixed-generation output within a single book as a deliberate cost/continuity tradeoff (one sentence in §9), or add a mitigation (e.g. a resume-time warning when the resume backend's generation differs from the segments already on disk). The design choice may be fine; the silence is the gap.

---

### IMPROVEMENT 4 — Fate of the existing model-resolution subsystem and its config keys is undefined

§6.2 introduces a new "typed model-profile registry", and §5.2 says invalid models are "rejected at argument or model-resolution time." But the SPEC never states what happens to the current resolution stack:

- `ModelResolver` with config-driven `model_aliases`, `fallback_chain`, `enable_fallback` (`ai/model_resolver.py:49-53`, `:58`, `:81-87`).
- `ModelProbe`, which `ModelResolver.resolve()` calls for availability (`ai/model_resolver.py:171-175`; probe wiring at `ai/model_resolver.py:93-106`).

§10 only says "remove Gemini-specific CLI probing in `ai/model_probe.py`" — but `ModelResolver` depends on `ModelProbe`, and §16 still lists `ai/model_resolver.py` with no disposition. Two questions the SPEC should answer explicitly:

1. Is `ModelResolver` **replaced** by the profile registry, or retained and adapted? If `ModelProbe`'s CLI probing is removed, `resolve()`'s probe branch breaks.
2. For an existing user `config.json` containing `model_aliases`, `fallback_chain`, `enable_fallback`, or `model_probe` — do these now **error, warn, or get silently ignored**? Because a `model_aliases` entry could reintroduce `lite` or an arbitrary model, this is part of the §5.2 safety contract, not a cosmetic detail.

**Recommendation:** Add a subsection (in §6 or §10) defining the disposition of `ai/model_resolver.py`, `ai/model_probe.py`, and each affected config key, and add an acceptance criterion that a legacy config with removed keys fails or warns rather than silently weakening the allowlist.

---

### IMPROVEMENT 5 — §3.4 overstates the current checkpoint limitation

§3.4 states the current schema "treats concrete `provider` and `model` values as compatibility keys" and that this "prevents a safe, user-authorized resume from Antigravity `flash` to Gemini API `flash`."

In fact `model` and `provider` are **soft** keys today: a mismatch prints a warning and is overridable with `--force-resume`, after which the prior translations **are** reused (`ai/cli.py:387-388`, `:397-404`, `:416`). A cross-provider resume is therefore already possible; it is merely gated behind `--force-resume`. The accurate problem statement is narrower and stronger: (a) `model` is stored as a **concrete string**, so there is no logical-profile equality across backends, and (b) `--force-resume` is **too coarse** — it simultaneously overrides prompt, segmentation, and batch-setting differences, so a user cannot authorize *only* a provider change.

**Recommendation:** Reword §3.4 to reflect that the capability exists but is coarse and concrete-string-based, so the rationale for schema v2 rests on the real gap rather than an overstated one.

---

### IMPROVEMENT 6 — Schema-v2 example (§9.3) does not match the real two-file layout, and run-level vs. per-segment provenance consistency is unspecified

The current checkpoint is **two files**: `state.json` (run metadata, including `model` and `provider`) and `translations.json` (`{schema_version, segments}`) — see `ai/cli.py:86-87` and `ai/cli.py:319-337`. The §9.3 example shows a single object that mixes `schema_version` with per-segment provenance; that maps onto `translations.json` but ignores `state.json`, which is where §9.2's compatibility keys actually live and where the resume check reads them (`ai/cli.py:319-331`, `:362-395`).

Adding per-segment `provider`/`backend`/`model` also introduces a new consistency question the SPEC does not resolve: how do the per-segment provenance values relate to the run-level `model`/`provider` in `state.json` that currently drive the compatibility check? Under a mixed-provider resume they will legitimately differ.

**Recommendation:** Show the v2 layout for **both** files and state which file holds the compatibility keys vs. the provenance records, so Phase 4 neither collapses the two files nor duplicates/contradicts the run-level fields.

---

## Notes (verified, not blocking)

The following SPEC claims were checked against the code and are accurate:

- Default model is the concrete `gemini-2.5-flash` (`ai/cli.py:436`); the SPEC's move to logical `flash` is a real, intended default change.
- `--cli-api-fallback` and `--fallback-provider api` exist and wire automatic paid fallback (`ai/cli.py:469`, `_CLIAPIFallbackAdapter` at `ai/cli.py:625-676`; `translatebook.sh:434,763,962`). Removal scope in §10 is justified.
- `GeminiProvider` shells out to `gemini --model <model> -p` via stdin (`ai/gemini_provider.py:62-63`).
- Segment IDs use the `"<doc_path>::<index>"` form the SPEC assumes, e.g. `EPUB/chapter01.xhtml::0` (`ai/adapters/sources/epub_adapter.py:153`).
- Checkpoint writes are atomic temp-file-then-replace (`ai/cli.py:305-310`); `--resume`/`--force-resume` already exist (`ai/cli.py:489`, `:501`).
- `00_extract_glossary.py` constructs providers directly, bypassing `ProviderFactory` (`00_extract_glossary.py:109-118`) — §6.5's "route through the same composition root" is warranted.
- Delimiter/segment-framing helpers are already shared (`ai/adapters/providers/_delimiter.py`, imported by `gemini_api_adapter.py:18-23`) — §6.4's "existing helpers remain shared" is correct.
- Current schema version is `1` (`ai/cli.py:84`), consistent with the v1→v2 migration framing.

One minor scope note worth adding to §10: `ai/epub_translate_roundtrip.py` still carries `cli_api_fallback_enabled` wiring (`ai/epub_translate_roundtrip.py:671,708`). CLAUDE.md marks it dead/reference-only, so it is not a runtime risk, but since §10 removes the fallback concept the SPEC should either list this module for cleanup or explicitly declare it out of scope.

---

## Prior Review Status

None — this is the first review of SPEC-020 (`v1`).
