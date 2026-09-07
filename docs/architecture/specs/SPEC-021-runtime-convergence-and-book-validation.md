---
specId: SPEC-021
title: Runtime Convergence and Book Validation
status: Ready for Implementation
priority: P1 - Core Feature
creationDate: 2026-09-07
lastUpdateDate: 2026-09-07
owner: User (AI-Assisted)
relatedSpecs:
  - SPEC-020
  - SPEC-005
  - SPEC-006
tags:
  - antigravity
  - checkpoint-resume
  - epub-validation
---

# SPEC-021: Runtime Convergence and Book Validation

## 1. Goal

Enable dependable EPUB translation through Antigravity and demonstrate usable translated books, preserved publication structure, and reusable work after interruption.

## 2. Baseline and authority

Production at `72e883b` still invokes Gemini CLI. The 2026-09-07 live probes passed for three synthetic segments with both delimiter and production tagged framing on Antigravity 1.1.27, requesting Flash 3.8 Low and Pro 3.1 Low. They do not establish book-length reliability.

This contract consolidates decisions from issues #15, #17, #18, and #19 and resolutions for #16, #20, #21, #23, and #24. The owner approved implementation after confirming a centrally changeable fixed model mapping, single-file checkpoints without a database, and per-invocation paid authorization. No issue is closed by this document.

Upon owner approval, this SPEC becomes the current implementation contract; SPEC-020 remains historical design input. In conflicts, this SPEC and the incorporated later issue resolutions take precedence. Preserve the historical source rather than implementing contradictory contracts simultaneously.

## 3. Proposed decisions

### 3.1 Application and model boundary

Retain the #15 application seam: `ai/orchestration.py` exposes `translate_epub`, `translate_markdown`, and `translate_pdf`, each taking `(input_path, output_path, options=None)` and returning a typed summary. A shared internal orchestrator owns pipeline construction. Group options by translation, model, provider, glossary, quality, and resume intent; exclude EPUB-only options from isolated-format types. Inject provider and checkpoint-store factories; preserve the existing source and provider ports without wrapping them again.

The CLI handles parsing, format detection, options construction, dispatch, and exit mapping. It must not import concrete providers or sources. Per #17, retry policy is decided at composition and injected into the provider-agnostic engine; the older #15 retry-wrapper suggestion is superseded.

Fixed model matrix, owned by one typed registry (`ai/model_profiles.py`). Version upgrades change this registry and its verification evidence, not scattered provider or CLI constants. Selection is frozen once per invocation:

| Public profile | Effort | Antigravity model ID |
|---|---|---|
| flash | low | gemini-3.8-flash-low |
| flash | medium | gemini-3.8-flash-medium |
| flash | high | gemini-3.8-flash-high |
| pro | low | gemini-3.1-pro-low |
| pro | high | gemini-3.1-pro-high |

**Proposed amendment to #19:** omitted effort resolves to `low`, rather than delegating to an external session default. This makes the requested default Flash 3.8 Low reproducible. `pro + medium` fails before launch. Explicitly pass both the concrete model ID and effective effort after testing their combined CLI semantics. Current probes used concrete IDs without a separate effort flag; the combined invocation still needs a live check. Medium/high entries were discovered but have not been translation-tested.

Validate a static typed profile/effort registry and the selected model's presence in `agy models` once per invocation. Fail on discovery failure or missing entries; never silently select another version or the active session model. Record CLI version, requested/effective effort, and concrete model. CLI 1.1.27 is the initial tested version; different versions require a compatibility probe before certification, not an assumption that discovery alone proves compatibility.

Gemini API keeps SPEC-020's explicit flash/pro mapping initially. Reject explicit API effort until a supported mapping is defined; never silently ignore an effort request. Effective API effort is recorded as unspecified, and changing effort remains a resume soft mismatch.

### 3.2 Transport and execution policy

Keep current EPUB `segment_tags` framing. Glossary requests retain their appropriate single-response protocol. Use current prompt assembly first; its older delimiter instructions overlap with tagged instructions, so extended probes must cover this before any prompt revision. Version any changed effective prompt for checkpoint compatibility.

Use a private, uniquely created temporary directory and prompt file, an argument-array subprocess, an explicit 600-second print timeout, and a 630-second outer timeout. Terminate and reap the owned process group on timeout. Clean prompt files on success and failure; retain sanitized diagnostics, not book text, in routine errors.

Raw providers perform one attempt; adapters frame, parse, and map typed errors without retry loops. Authentication, capacity, network, timeout, empty output, and artifact-only output halt CLI execution without splitting or API fallback. Only content/protocol failures may split under the engine's bounded policy (maximum depth 10). Preserve sanity validation before checkpoint persistence. A nonzero exit or a known terminal false-success response cannot count as a translation. Do not scan source-like text indiscriminately for words such as "authentication" and misclassify legitimate translated prose.

### 3.3 Checkpoint durability

**Proposed choice: a single schema-v2 checkpoint document** containing compatibility metadata, segment text/provenance, and audit summaries. This replaces independently updated `state.json` and `translations.json` on new writes.

| Alternative | Benefit | Cost | Proposal |
|---|---|---|---|
| Single atomic document | Metadata and translations commit together; simple recovery | Rewrites accumulated state each successful batch | Adopt initially |
| Generation directories plus pointer | Immutable generations and rollback | More recovery and retention machinery | Defer |
| Journal or SQLite | Incremental writes | Additional replay/transaction and migration semantics | Defer until measured need |
| Two independent replacements | Smallest code change | Can expose mismatched metadata and translations | Reject |

Write a unique temporary file in the same directory, flush and fsync it, atomically replace the canonical document, then fsync the directory where supported. Fail visibly on durability errors. Acquire an exclusive run-level checkpoint lock before loading and hold it through completion; a second writer fails clearly. Uncommitted temporary files never become recovery candidates automatically.

Read legacy v1 files without modifying them. Validate structure, segment membership, and available count evidence; ambiguous or malformed legacy state fails loudly rather than starting over or inventing provenance. Import recognized flash/pro identities with known legacy provenance; unknown/lite mappings need explicit force with a selected profile. Do not infer missing authoritative compatibility evidence as a match. Write v2 only after a new validated batch, leaving v1 intact. Prefer v2 thereafter; a corrupt v2 must not silently fall back to older v1.

Absolute-hard mismatches: input hash/format and segmenter signature. These cannot be forced. Soft mismatches: language, profile, effective effort, effective prompt/glossary hash, protocol version, and batching parameters. These require `--force-resume`. Concrete provider/model changes alone are audit-only, with a mixed-model warning. Mismatch errors stop rather than silently retranslating. A fully restored run makes zero translation calls and can rebuild the output without rewriting the checkpoint. An API run with no remaining billable work needs no paid authorization.

An interrupted or invalid batch never replaces the last valid checkpoint. Power-loss durability is claimed only to the extent covered by the filesystem contract; injected failures establish process-level crash consistency.

### 3.4 Paid execution

Remove automatic CLI-to-API fallback. Retain an erroring migration stub for `--cli-api-fallback`. Every billable invocation requires explicit `--provider api` plus exact interactive `USE_API` confirmation or `--allow-paid-api` for non-interactive execution. Config, environment, and checkpoints cannot authorize spending. Authorization precedes provider construction and every potential glossary/API path; it covers this invocation only.

Show estimated remaining source volume and mixed-model continuity warning. If glossary generation itself needs API work, include it in the authorization scope before calling it. Use one SDK/network attempt, one raw-provider attempt, and zero engine split depth for paid batches; failures halt. Persist available usage as audit data, distinguishing unavailable token counts from zero.

**Proposed resolution of #24's QuotaTracker wording:** do not use the current daily-usage accumulator as authorization or a hard spending cap. It records usage but has no reservation or concurrency contract. Per-invocation consent plus bounded attempts enforces this migration's boundary; a monetary budget service remains out of scope, as in SPEC-020. This is a deliberate departure from the ticket title, requiring owner acceptance.

### 3.5 Configuration and retirement

Implement #19's strict JSON schema and removed-key migration errors, including schema/loader key parity. Keep only flash/pro public profiles, remove size-driven model switching, and stop reading the example config as production defaults. Preserve ignored user config; report actionable migration steps without rewriting it.

EPUB is the supported CLI surface. Retain Markdown/PDF adapters behind `--allow-isolated-format`; reject DOCX and unknown formats. Preserve default-on EPUB resume and the explicit-resume error on isolated runs. Retire legacy shell and numbered Markdown orchestration only after the new entrypoint passes its gates, using Git recovery anchors and separate deletion review. Keep baseline EPUB tooling and evaluation assets. Do not reintroduce the orphaned legacy translation module to accelerate the migration.

## 4. Implementation phases

- [ ] **S1 — Application seam:** move orchestration under the approved boundary with behavior tests and thin-CLI/three-argument fitness checks. Preserve runnable EPUB behavior throughout extraction.
- [ ] **S2 — Checkpoint:** implement the atomic document, lock, compatibility tiers, legacy import, provenance, and fault-injection tests.
- [ ] **S3 — Runtime and authorization:** implement typed model registry, Antigravity transport/adapter, typed engine policy, paid authorization, and removal of automatic fallback. Route glossary through the same construction and authorization boundary.
- [ ] **S4 — Public contract:** implement strict config, migration errors, format isolation, documentation, and tested default Flash 3.8 Low selection. Only now advertise Antigravity as the default runtime.
- [ ] **S5 — Live acceptance:** verify combined model/effort flags, a near-limit synthetic batch, a small actual EPUB through the public command, and interrupted/resumed execution. Then execute the book matrix below.
- [ ] **S6 — Retirement and delivery:** independently review risky changes, fix findings, retire obsolete paths behind deletion gates, and present final diff and evidence. Commit/push/merge remain subject to existing owner approval rules.

## 5. Acceptance criteria

- [ ] Default `uv run bookweaver INPUT --output OUTPUT` invokes verified Flash 3.8 Low through Antigravity and records concrete provenance.
- [ ] Missing models, invalid combinations, authentication, timeout, capacity, and malformed output follow tested failure behavior without paid fallback.
- [ ] Timeout tests prove owned-process cleanup and prompt-file removal.
- [ ] Every paid path, including glossary work, proves zero unauthorized calls and no multiplied attempts on failure.
- [ ] Checkpoint tests inject failures before/after replacement, reject a concurrent writer, preserve committed segments, import valid v1 data, reject corrupt state, and prove zero calls for full resume.
- [ ] Cross-provider resume reuses matching segments and retains actual per-segment provenance; soft and hard mismatch rules are separately tested.
- [ ] Config-schema/loader parity, CLI import boundaries, isolated-format gates, and obsolete-runtime deletion checks pass.
- [ ] `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest -q` pass. Shell syntax checks apply until shell retirement; compile changed Python modules. Run the repository architecture gate where configured.
- [ ] A small EPUB completes through the production composition with real Antigravity; no fake provider is used as live acceptance evidence.
- [ ] Each selected book has its source hash, exact model/effort, prompt hash, batch settings, duration, checkpoint counts, output path, structural checks, and manual review recorded.

Book matrix: one narrative title, one terminology-heavy title, and one complex-layout publication (the local Economist issue is a candidate). Titles and source paths must be selected before external content transmission. Start with independently packaged one-to-two-chapter samples because the current `--only-docs` is not implemented; preserve the original books. Full-book runs follow successful samples.

For each output: zero missing/reordered translated segment IDs; zero new broken manifest assets or fragment links relative to input; unchanged source resources outside intended bilingual content changes; readable table of contents, images, links, footnotes, and alternating text. Tables remain source-only under the existing contract. Manually review at least 20 distributed passages per book plus every detected anomaly; allow zero meaning-reversing, omitted, or invented material in the reviewed sample. Report sampling limits and stylistic observations separately. Verify one controlled interruption/resume per title with zero new provider calls for already committed segments.

These criteria prove the tested books and configurations, not universal translation quality. No live Gemini API acceptance is required or authorized by this plan.

## 6. Status history

| Date | Status | Note |
|---|---|---|
| 2026-09-07 | Draft | Consolidated existing decisions and proposed remaining contracts for owner review; no production migration implemented |
| 2026-09-07 | Ready for Implementation | Owner approved the defaults, centrally maintainable mapping, single-document checkpoint, paid authorization, and implementation |

## 7. Related

- [Runtime convergence #13](https://github.com/austery/BookWeaver/issues/13)
- [Application seam #15](https://github.com/austery/BookWeaver/issues/15), [checkpoint #16](https://github.com/austery/BookWeaver/issues/16), [execution policy #17](https://github.com/austery/BookWeaver/issues/17)
- [Format lifecycle #18](https://github.com/austery/BookWeaver/issues/18), [CLI/config #19](https://github.com/austery/BookWeaver/issues/19), [lineage #20](https://github.com/austery/BookWeaver/issues/20)
- [Gates #21](https://github.com/austery/BookWeaver/issues/21), [probe #22](https://github.com/austery/BookWeaver/issues/22), [provider #23](https://github.com/austery/BookWeaver/issues/23), [paid path #24](https://github.com/austery/BookWeaver/issues/24)
- [Live probe and baseline evidence](../../plans/2026-09-07-antigravity-protocol-probe.md)
- [Historical SPEC-020](SPEC-020-antigravity-cli-migration-and-paid-api-authorization.md)
- Current code: `ai/cli.py`, `ai/core/engine.py`, `ai/provider_factory.py`, `ai/quota_tracker.py`, `ai/adapters/providers/_delimiter.py`.
