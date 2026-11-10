---
specId: SPEC-029
title: Resume Session — one module for checkpoint verify, restore and commit
status: Approved by the owner (2026-11-10) — three-step delivery (§5) and interface (§2.1), including the tach.toml change; §6 item 2 approved for PR B; §6 item 3 kept as is
implementationStatus: Step 1 merged (PR 108); PR A merged (PR 110); PR B implemented on branch claude/spec-029-resume-session-module
priority: P2 - Reliability
creationDate: 2026-11-10
lastUpdateDate: 2026-11-10
owner: User (AI-Assisted)
relatedSpecs: [SPEC-021, SPEC-024, SPEC-025, SPEC-028]
tags:
  - checkpoint
  - resume
  - refactor
  - deep-module
---

# SPEC-029: Resume Session

## 0. Summary for the owner

- **What does not change:** the checkpoint file, its location, its identity fields, the resume rules, the error messages, and every saved book. An existing checkpoint resumes exactly as before.
- **What changes:** the code that drives resume moves out of `TranslationOrchestrator.translate` into one module, `ai/resume.py`. Today its rules hold only because statements sit in the right order inside a 340-line method. After the move, the module enforces the order itself, and tests check the rules directly.
- **Why now:** resume protects finished work when a CLI fails mid-book. The owner rates it as critical (2026-11-10). The risk is a later edit that moves one line.
- **A real gap found during review (§6):** one blank segment in a model reply is saved, and then every later load refuses the whole checkpoint, even with `--force-resume`. Reproduced offline on main (0c702bf). This is a behaviour fix, separate from the move, and recommended first.
- **Delivery in three steps (§5):** fix the blank-segment gap; add tests that pin today's behaviour, on main, with no code move; then move the code with those tests unchanged.

## 1. Problem

Resume works, and tests pin its behaviour. The problem is where the rules live. In `ai/orchestration.py` on main (0c702bf):

| Rule | Where it holds today |
|---|---|
| R1. Validate the whole checkpoint document and its hard identity fields (book bytes, format, segmenter) before any external work, including term extraction. Soft fields are not checked yet. | A `store.load(..., hard_only=True)` call placed before `plan_glossary` (about lines 301-322); the load validates every record and the segment count (`ai/checkpoint_store.py` `load`). |
| R2. Refuse a resume that crosses a Codex or Claude Code model unless `--force-resume`. | `_refuse_trial_model_change(saved, model)` right after R1 (lines 147-165, 321-322). |
| R3. The prompt hash is known only after the glossary is chosen; only then load the full checkpoint. | `identity = replace(identity, system_prompt_hash=...)` then a second `store.load` (about lines 358-369). |
| R4. Warn when restored segments came from another model. | A `print` after the second load (lines 370-374). |
| R5. Save after each validated batch: the whole record map, with provenance read from the real provider (not the deferred wrapper) at commit time; record paid usage for metered providers; keep earlier runs' usage. | A positional `SegmentRecord(...)` call inside the `persist` closure (lines 446-471); `factory.usage_snapshot()`; the store keeps `paid_usage_by_run` from its `load`. |
| R6. The identity's batch bounds equal the engine's batch bounds. | Two sources: the identity reads `SEPARATOR_OVERHEAD` from `_delimiter.py`; `EngineConfig` uses its own default `6` (`ai/core/engine.py:36`). They agree by coincidence. |
| R7. The local API reads progress from the checkpoint. | `ai/local_api.py` `_done_segments` parses `checkpoint.json` itself (about lines 311-319). |

Other symptoms:

- `identity is not None` is checked four times, and `content_signature is not None` once; all are always true (`_compute_content_signature` returns `str`).
- A store exists when `resume.enabled or resume.force`, so `--no-resume --force-resume` still restores. `store is not None` decides glossary reuse (`may_reuse`), the location of `warnings.json` and `term-consistency.json`, the full load and the save. No test covers the force-only case.
- Each rule can only be tested through a whole EPUB run with provider fakes.

## 2. Decision

Add one deep module, `ai/resume.py`, with a small interface. The orchestrator calls it; nothing else in `translate` touches `CheckpointStore` or `CheckpointIdentity`.

### 2.1 Interface (shape, not final code)

```text
open_resume_session(
    store_factory,
    directory | None,                       # None exactly when not (resume.enabled or resume.force)
    book: content signature, legacy signature, segment ids,
    selection: ResolvedModel, requested effort, output language,
    bounds: BatchBounds (chars, segments, separator overhead),
    segmenter_signature,                    # injected: ai.resume cannot import ai.orchestration
    force: bool,
    usage_snapshot: callable | None,        # injected from the provider factory; metered runs only
) -> ResumeSession                          # a context manager

session.verify() -> Verified                # R1 + R2 + early soft check; returns may_reuse and the hard-load records
session.restore(verified, prompt_sha256) -> dict[segment id, SegmentRecord]   # R3 + R4
session.commit(batch, provider) -> None     # R5; provider = the real delegate, not the wrapper
session.directory -> Path | None            # where warnings.json and term-consistency.json go
session.last_save_bytes, last_save_seconds  # for the [progress:checkpoint] line

checkpoint_progress(directory) -> int | None    # R7; no lock, no validation; missing 0, unreadable None
```

- **`verify` returns the value the glossary step needs.** `plan_glossary` takes `may_reuse` from the `Verified` value, and `restore` takes the `Verified` value as an argument. Term extraction then cannot be planned, and the full load cannot run, without `verify` having run first. This makes R1 and R2 structural instead of positional. `commit` raises if `restore` has not run.
- **No-resume is the same interface.** Without a directory the session creates no directory, lock or file; `verify` returns `may_reuse=False` and no records; `restore` returns nothing; `commit` does nothing; `directory` is `None`.
- **Early soft check (owner decision, 2026-11-10).** Unless forced, `verify` also compares every soft identity field except `system_prompt_hash` (language, profile, effort, protocol, batch characters, separator overhead, batch segments) and raises the same `CheckpointMismatchError` before any external work. The prompt hash is still checked in `restore`, because it depends on the glossary. This is the one intended behaviour change in PR B: the same refusal, earlier. PR A pins today's late refusal; PR B updates that one test and states it in the PR.
- **`BatchBounds`** is one frozen value built once from the options and configuration. Both the identity and `EngineConfig` read it, and `EngineConfig` receives `separator_overhead` explicitly (R6).
- **`commit`** builds `SegmentRecord` with keyword arguments, reads `backend` and `runtime_version` from the delegate at commit time, takes usage only for metered providers, saves the whole map with the current identity on the same store instance as `verify` and `restore`, updates its records only after a successful save, and lets a save failure stop the run.
- `checkpoint_progress` is re-exported by `ai/orchestration.py`, because tach lets `ai.local_api` import only `ai.orchestration`.

### 2.2 What moves

From `ai/orchestration.py` into `ai/resume.py`: `_refuse_trial_model_change`, `_segment_backend`, the identity construction with its `"pending-prompt"` placeholder, both `store.load` calls, the mixed-model warning, `SegmentRecord` construction, and `_resolve_checkpoint_dir` with `_CHECKPOINT_ROOT`. `_ACTIVE_EPUB_SEGMENTER_SIGNATURE` stays beside the segmenter's owner and is passed in. `default_epub_checkpoint_dir` stays in `ai/orchestration.py` as a thin public function that calls the moved code. The `[progress:checkpoint]` line stays in the orchestrator and reads the session's save metrics.

From `ai/local_api.py`: `_done_segments` calls `checkpoint_progress` instead of parsing the file.

### 2.3 What does not move or change

- `ai/checkpoint_store.py` (file format, lock, legacy v1 import, validation) — unchanged, except one optional keyword on `load` (§6a).
- `ai/term_extraction.py` and the glossary call — unchanged; `translate` still calls `plan_glossary` between `verify` and `restore`.
- The sanity probe, the invocation audit, `DeferredProvider` — unchanged (owner decision 2026-11-10: not worth refactoring).

## 3. Invariants that must stay byte-identical

| Item | Current value or source |
|---|---|
| Identity field order and names | `CheckpointIdentity` in `ai/checkpoint_store.py` (unchanged file) |
| `input_format` | `"epub"` |
| `segmenter_signature` | `_ACTIVE_EPUB_SEGMENTER_SIGNATURE` = `epub-leaf-block-v4-source-only-bibliography` |
| `protocol` | `"segment_tags"` |
| `separator_overhead` | `6` (`SEPARATOR_OVERHEAD`) |
| Batch defaults | 60,000 characters (Pro and Flash), 200 segments, and the configuration keys that override them |
| `system_prompt_hash` | SHA-256 of the rendered prompt, set after the glossary is chosen |
| Checkpoint directory | `--checkpoint-dir`, else `<output dir>/.bookweaver_checkpoints/epub/<book stem>` |
| Error messages | Text of every `CheckpointMismatchError` and `CheckpointError` the user can see |
| Lock lifetime | Taken before the first load; held through the output EPUB write, `term-consistency.json` and the sanity summary; released before the invocation audit is written (the audit finalizer is registered before the session opens) |
| Caller order kept outside the session | The sanity warning for a batch is recorded only after that batch's `commit` succeeds |
| Full restore | Builds no provider, asks no paid consent, writes zero checkpoint bytes |
| `[progress:checkpoint]` | Same line and fields: `bytes`, `seconds`, `segments` |

## 4. Verification

1. **Existing behaviour tests stay unchanged and pass**, in particular: `test_checkpoint_preflight_precedes_glossary_requests`, `test_content_change_with_same_metadata_cannot_restore`, `test_identical_content_moved_and_touched_can_restore`, `test_cross_provider_resume_preserves_provenance_and_paid_noop`, the Codex and Claude Code resume tests in `tests/unit/test_invocation_audit.py`, `test_interrupted_epub_restores_only_committed_batches`, and `tests/unit/test_checkpoint_store.py`.
2. **Pin today's behaviour first, on main, before any move** (PR A). Each test goes through `TranslationOrchestrator` and must pass on main:
   - a second store on the same directory is refused while the provider runs and while the output is written;
   - a lock held from outside makes `translate` fail with `CheckpointError` and write exactly one audit;
   - `ResumePolicy(enabled=False, force=True)` on a finished book restores every segment, makes zero requests and reuses the glossary;
   - one full saved record compared with a literal (all fields, including `effort`, `requested_effort`, `runtime_version`);
   - the whole `CheckpointIdentity` for default options compared with a literal;
   - two metered runs with different run ids, the first interrupted: both usage entries survive;
   - an unknown segment ID and a wrong segment count, with extraction requested: zero provider requests;
   - a failed checkpoint save on a suspicious batch: `warnings.json` does not list that batch;
   - a no-resume run creates no `.bookweaver_checkpoints` and leaves an existing `checkpoint.json` unchanged;
   - the `[progress:checkpoint]` line and its three fields;
   - `done_segments` for a corrupt `checkpoint.json` is `None`.
3. **New tests on the session interface** (PR B; real `CheckpointStore` in a temporary directory, no EPUB, no provider): `restore` without a `Verified` value cannot be called; `commit` before `restore` raises; a hard mismatch raises in `verify`; the trial-model stop and `--force-resume`; the mixed-model warning; no-resume writes nothing; `checkpoint_progress` on a missing, valid and corrupt file.
4. **Cross-version resume** (PR B), with zero provider calls counted across translation and extraction:
   - main writes a partial checkpoint, the branch continues it; the final `checkpoint.json` and output equal main's own continuation apart from `completed_at`;
   - a fresh checkpoint from the branch equals one from main field by field and in key order;
   - the reverse direction: the branch writes, main resumes (so a revert is safe);
   - a run with a glossary cache written by main and reused by the branch;
   - a metered checkpoint with an earlier `paid_usage_by_run` entry; an identity without `max_batch_segments`; records without the optional fields; historical `api` and `gemini_api` provenance;
   - a forced resume across a soft mismatch, a trial-model stop, and a mixed-model checkpoint, each written by main;
   - a legacy v1 directory: the same refusal text as main and untouched files (v1 always recorded segmenter v3, which the active v4 refuses even with force);
   - a copy of one real book checkpoint from the owner's library: verify and restore with zero calls and an identical output EPUB;
   - local API `done_segments` on a main-written checkpoint while a run holds the lock.
5. ruff, format, `tach check`, `scripts/verify_installed_runtime.py`, and the full suite.
6. Independent Risk, Standards and Spec reviews; Structure is touched (`tach.toml` gains `ai.resume`), so the owner approves the merge. `docs/agents/impact-radius.md` (lines about 53-78) names the old locations and is updated in PR B.

## 5. Delivery and coordination

1. **Blank-segment fix** (separate behaviour change, §6 item 1). Recommended first, because it protects saved work today.
2. **PR A: pin tests on main** (§4.2). No code move. Tests must pass on main unchanged.
3. **PR B: the move** (§2), with PR A's tests unchanged, the cross-version check (§4.4), and the `tach.toml` entry: `ai.resume` depends on `ai.checkpoint_store`, `ai.model_profiles`, `ai.ports`; `ai.orchestration` adds `ai.resume`.

SPEC-028 Phase 2b (`--term-panel`, issue 100, session "Session Handoff 阶段 2b") edits `translate` at the `plan_glossary` call and has agreed to keep that call between the hard-only load and the prompt hash. PR A and PR B start after Phase 2b merges.

## 6. Gaps found during review (the move neither causes nor fixes them)

1. **A blank segment makes the checkpoint unloadable.** A multi-segment `segment_tags` reply may contain an empty body; the parser returns `""` (`ai/adapters/providers/_delimiter.py`; pinned by `test_segment_tags_allows_empty_segment_body`), the engine checks only the count (`ai/core/engine.py`), and the sanity probe only warns. The batch is saved, and every later load raises "Invalid empty checkpoint translation", even with `--force-resume`. Reproduced offline on main (0c702bf): run 1 translated 2 segments, run 2 failed with `CheckpointError`. Proposed fix: treat a blank translation as a failed batch before it reaches the checkpoint, so the existing split-retry handles it, and never write a record the next load refuses. Owner decision: it changes provider and engine behaviour.
2. **Soft mismatches are refused late.** Effort, profile, language and batch caps are known before term extraction but refused only at the full load, after extraction may have spent quota or money. Approved by the owner (2026-11-10): check them in `verify` when not forced, in PR B (§2.1).
3. **A non-trial model change only prints a warning** (Antigravity models, metered vendors; SPEC-021, SPEC-024). Recorded decision (SPEC-020 §9.2: a same-profile provider change should not need the coarse `--force-resume`). The owner confirmed on 2026-11-10 to keep it: it lets a book finish on another model when quota runs out or a model version changes; each record keeps its model, and the run prints a mixed-model warning.
4. **`--no-resume` rewrites the glossary cache** that an unfinished checkpoint in the same folder depends on, and takes no lock.
5. **A forced resume leaves no trace in the records**: they carry no prompt hash, so later plain resumes can mix prompts without a signal unless the model id differs.
6. **Split halves are not committed**: a successful left half is translated again when the right half fails (subscription runtimes).
7. **No per-segment source digest**: segment IDs are positional; only the book hash and the hand-bumped segmenter constant guard their meaning.

## 6a. Implementation notes (PR B)

- **One deviation from §2.3:** `CheckpointStore.load` gains an optional `deferred` keyword that skips the named soft fields. `verify` uses it to check every soft field except `system_prompt_hash` before term extraction. Without the keyword the load behaves as before; the file format and validation are unchanged.
- **Error text:** a soft mismatch now names only the fields known at `verify` (for example `Checkpoint mismatch: effort`). When the prompt also changed, `restore` reports it afterwards; before, one late message listed all fields together. A changed output language always changes the prompt, so its message no longer lists `system_prompt_hash`. This is the one exception to the error-text row in §3.
- **Other consequences of the early check** (independent review, 2026-11-10; all for a non-forced run with a soft mismatch): a failing term extraction or Term Panel no longer hides the mismatch; the invocation audit of the refused run names the translation model, with no extraction model or panel; no `[glossary]` lines are printed and no glossary cache is written; an invalid glossary request (for example `--term-panel` with `--glossary`) is reported after the mismatch, not before. A non-forced run reads the checkpoint three times instead of twice.
- **Interface shape versus §2.1** (shape, not final code): the session is built with the `ResumeSession(...)` constructor and entered as a context manager; `commit` returns whether it saved (for the progress line); `saved_segments` reports the saved count; `Verified` carries only `may_reuse`; `usage_snapshot` is required and is called only for metered models. `plan_glossary` still takes `may_reuse` as a plain value, so the guarantee that `verify` runs first is the data dependency at that call, not a type.
- **Verification evidence (§4.4):** recorded in the PR B description: main and branch in both directions, glossary cache reuse, metered usage, an identity without `max_batch_segments`, historical provenance, forced resume, the trial-model stop, a mixed-model checkpoint, a legacy v1 directory, local API progress under a held lock, and two real books from the owner's library.

## 7. Alternatives

- **Leave the code as it is.** The ordering rules hold today and most are tested. Rejected by the owner's priority: resume is critical, and order-by-statement is the most likely way to break it in a later edit.
- **Move the rules into `CheckpointStore`.** Rejected: the store would need to know presets, trial runtimes and the provider port. It is a clean file-format module today, and `ai.checkpoint_store` has no tach dependencies.
- **One `load` that takes the glossary as a callback.** Rejected: it hides an external call inside the checkpoint module and makes R1 harder to see.

## 8. Open questions for the owner

1. ~~Fix the blank-segment gap first~~ — approved and merged (PR 108, 2026-11-10).
2. ~~Approve the three-step delivery and the interface~~ — approved by the owner, 2026-11-10.
3. ~~Check soft mismatches before term extraction~~ — approved for PR B, 2026-11-10.
4. ~~Keep the warning-only rule for non-trial model changes~~ — kept, 2026-11-10.
