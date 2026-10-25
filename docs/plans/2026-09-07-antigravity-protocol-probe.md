# Antigravity migration: initial live protocol evidence

## Objective

Complete the Antigravity migration and validate representative EPUB books for translation quality, layout preservation, and interruption/resume behavior. This report is initial probe evidence, not migration acceptance.

## Verified baseline

- Date: 2026-09-07.
- Repository: `72e883b`, clean `main` matching fetched `origin/main` before this report.
- The production factory still creates `GeminiProvider`; its command still invokes `gemini`.
- Runtime-convergence issues are design decisions, not delivered implementation.
- Installed Antigravity CLI: `1.1.27`.
- Live model discovery includes `gemini-3.8-flash-low` and `gemini-3.1-pro-low`; the old Flash 3.5 mapping is absent.

## Authorized delimiter probe

Two live subscription-runtime calls used a temporary prompt file containing three synthetic English passages: a key and garden gate, checkpoint recovery, and a telescope observation. The wrapper requested three Chinese translations separated by `%%`, returned inline without commentary or file creation. Each call used `--print-timeout 120s` and a 150-second outer timeout.

| Selected model | Exit | Elapsed | Result |
|---|---:|---:|---|
| `gemini-3.8-flash-low` | 0 | 6.7 s | Three ordered, non-empty Chinese translations; no fences or artifact links |
| `gemini-3.1-pro-low` | 0 | 15.7 s | Three ordered, non-empty Chinese translations; no fences or artifact links |

Output was inspected manually for order and checked mechanically for count, CJK presence, and absence of fences/artifact markers. This verifies a tiny delimiter probe only. It does not certify long batches, model identity beyond the requested CLI argument, EPUB packaging, or resume.

Temporary raw evidence: `/private/tmp/bookweaver-agy-probe-20260907/`, including `run.py`, `prompt.txt`, and per-model stdout/stderr. These local temporary files are not durable repository assets.

## Material discrepancies

1. Issue #22 describes `%%` as the EPUB protocol. The current composition root passes `use_segment_tags=fmt == "epub"` (`ai/cli.py`); EPUB uses the tagged protocol. The delimiter probe does not discharge that production-path gate.
2. Old ticket model names have drifted. Concrete profile/effort mapping still requires a decision; the probe's Flash 3.8 choice is not an approved permanent registry mapping.
3. SPEC-020 predates later decisions, including orthogonal effort and strict CLI/config changes. Reconcile these before production implementation.
4. The handoff's uncommitted Model Profile note is stale: commit `72e883b` contains it.

## Production tagged-protocol probe

A proposed two-model probe using `build_system_prompt(..., immersive=True)` and the existing `segment_tags` framing/parser was initially rejected before execution by automatic approval review. The owner subsequently explicitly authorized transmission of the repository translation prompt with the three synthetic passages. The probe then executed successfully on 2026-09-07.

The prompt was assembled using the current `build_system_prompt`, `augment_prompt_for_batch`, and `join_segments` functions. Both outputs were checked by the existing `split_response` parser, with additional CJK, exit-code, fence, and artifact-link checks. Manual inspection confirmed the three original meanings remained in order and the raw IDs were exactly 1, 2, 3.

| Selected model | Exit | Elapsed | Result |
|---|---:|---:|---|
| `gemini-3.8-flash-low` | 0 | 10.3 s | PASS: three non-empty Chinese segment blocks, IDs 1–3, no extra prose or fences |
| `gemini-3.1-pro-low` | 0 | 19.1 s | PASS: three non-empty Chinese segment blocks, IDs 1–3, no extra prose or fences |

Raw artifacts reside alongside the earlier evidence as `tagged.py`, `tagged-prompt.txt`, and per-model `*.tagged.stdout.txt` / `*.tagged.stderr.txt`.

Decision supported by this bounded evidence: retain the existing tagged EPUB protocol for the next migration slice; no protocol redesign is indicated by these samples. This is not proof of 60K-character batch fidelity, sustained book-length reliability, or flawless translation. For example, Flash's rendering of the key as pressed beneath the cup adds a slight spatial nuance absent from the source.

## Next gate

Settle the remaining checkpoint, provider, authorization, and implementation/deletion contracts before claiming migration readiness. No Gemini API calls or full-book translations were made. The offline test-suite result is recorded below; it does not validate an implemented Antigravity adapter.

## Offline baseline follow-up

- `ruff check .`: passed.
- `ruff format --check .`: initially failed on trailing whitespace in two docstring blank lines. Backed up both files under the temporary evidence directory, removed only that whitespace, and reran successfully (91 files formatted).
- `bash -n translatebook.sh`: passed.
- Contributor-guide compilation check for six named Python modules: passed.
- `git diff --check`: passed before this report update.
- Full `uv run pytest -q`: 522 passed, 1 skipped, 4 warnings in 164.12 seconds. Warnings report existing model-resolution fallback to the primary model when all candidates are unavailable; they are not Antigravity validation. The skipped case requires the external-regression opt-in.

The local `2_TheEconomist.2026.04.18.epub` contains 2,247 extracted segments across 100 translatable documents, totaling 587,955 source characters; the archive contains 126 image entries. ZIP integrity passed. The baseline roundtrip command completed with 102 spine items, and an independent ZIP comparison confirmed identical entry names, order, and uncompressed bytes. Output: `/private/tmp/bookweaver-agy-probe-20260907/economist-baseline.epub`.

This proves local extraction and zero-mutation repackaging for this sample, not bilingual rendering or live translation quality. The baseline validator only collects `application/xhtml+xml` documents for fragment checks; byte equality is the stronger preservation evidence here and does not validate source links declared as `text/html`.

## Implementation progress after owner approval

The owner approved centrally maintainable fixed model mappings, a single-file checkpoint without a database, per-invocation paid authorization, and implementation under SPEC-021.

Implemented in the working tree (not committed or delivered):

- A central typed model/effort registry, initially Flash 3.8 Low; unsupported combinations fail loudly.
- An Antigravity adapter with live model discovery, certified CLI version checking, explicit effort, private prompt files, outer process-group timeout, cleanup, and typed non-splittable infrastructure failures.
- Format-specific application entrypoints and thin CLI dispatch. Provider and checkpoint factories are injectable. Legacy internal helpers remain pending gated retirement.
- A locked single-document checkpoint, atomic replacement and synchronization, legacy import, compatibility tiers, segment provenance, save size/timing, and rejection of corrupt/empty restored translations.
- Strict configuration validation; example settings no longer serve as runtime defaults. The local ignored configuration is not automatically changed.
- A shared paid provider factory for main translation and standalone glossary extraction. Explicit authorization precedes client construction; SDK attempts are constrained to one. Per-request available usage is written independently of checkpoints, with unknown counts retained as null and individual request records preserved.

Independent standards/spec review found glossary-cache identity, blank restored translations, CLI-version provenance, conflicting legacy templates, and incomplete usage persistence. Fixes bind glossary cache paths to source and extraction settings, reject invalid restored records and conflicting templates, record CLI version and requested/effective effort, and add independent run audit files. This is interim review evidence, not final acceptance of all migration requirements.

### Real adapter and application evidence

1. New adapter with both `--model gemini-3.8-flash-low` and `--effort low`: three synthetic translations passed on agy 1.1.27.
2. New `translate_epub` composition with an explicitly empty configuration: a two-segment synthetic EPUB completed through real Antigravity and produced alternating source/Chinese content. Checkpoint save was 1,178 bytes and approximately 0.0005 seconds in this small run. A second invocation restored both segments with zero pending batches. This run preceded the later audit-field additions.
3. Local package validation reported no errors, and source paragraphs plus Chinese content were present in the output. This is not EPUBCheck or visual reader certification.
4. Near-limit real adapter probe: 135 synthetic segments, 58,542 source characters, 135 non-empty CJK outputs, 87.17 seconds. First/middle/last samples retained the observation numbers and facts; length ratios ranged from 0.314 to 0.323. This is a repeated-structure synthetic test, not representative-book quality evidence.
5. An offline application integration test injects a transport interruption in batch two, then proves only batch two is requested on resume while batch one is restored.

Additional temporary evidence: `provider-live.py`, `epub-live.py`, `synthetic-book.epub`, `synthetic-translated.epub`, `large-probe.py`, `large-source.json`, and `large-translated.json` under the temporary evidence directory.

### Outstanding acceptance and user-owned state

- With explicit owner approval, the ignored `config/config.json` was migrated and validated. The original is backed up with mode 0600 at `/private/tmp/bookweaver-agy-probe-20260907/config.original.20260907125517.json`; credential values were neither printed nor committed. Formerly unused prompt-profile settings were omitted to preserve built-in prompt behavior.
- The default CLI entrypoint passed a real synthetic EPUB run using migrated local configuration, including enabled glossary extraction. Without model/effort flags it selected `gemini-3.8-flash-low` / `low`; two segments completed in one batch. A second invocation restored both segments with zero pending batches. The checkpoint was 1,336 bytes and took approximately 0.0012 seconds to save. Evidence: `default-cli-translated.epub` and `default-cli-checkpoint/` in the temporary evidence directory.
- Representative narrative/technical book paths and permission to transmit their contents remain pending. No full real-book translation was performed.
- Legacy retirement, complete schema-consumer parity coverage, further crash/audit tests, and final review/acceptance remain incomplete. Do not mark the migration complete from the small EPUB or large synthetic probe.

### Latest verification checkpoint

- Full suite during implementation: 554 passed, 1 skipped, 4 legacy-model-resolution warnings in 166.02 seconds.
- Subsequent audit/application changes: 8 targeted tests passed; the interruption and CLI import-boundary tests are included in the application suite.
- Latest lint, formatting, architecture, changed-module compilation, and retained-shell syntax checks passed. No commit, push, merge, or live paid API call occurred.
- Usage audit was further strengthened after review: request records contain model, framing protocol, pending/responded/failed state, and individual nullable token counts; pending state is saved before the SDK call, and audit replacement synchronizes the directory. This retains partial known usage even when aggregate totals are unknown.

- Final independent audit re-review found no new draft-PR blockers; its 24 relevant offline tests passed. Whole-book acceptance and legacy retirement remain open.

- Final current-tree regression: 556 passed, 1 skipped in 165.82 seconds. Ruff lint/format, Tach architecture checks, shell syntax, and Git whitespace checks passed.
