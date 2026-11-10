# Impact radius map

**North Star:** `/Users/leipeng/Documents/research-notes/05-archive/2026-11-08_bookweaver_north-star-and-product-lineage.md`.
Agents read only its `## Current core` section (confirmed by the owner on
2026-11-08).

Trunk below follows from its mission and intended form: turn a book the owner
wants to read into a faithful, complete, terminology-accurate, alternating
bilingual EPUB. Terminology is the core difficulty: the model reads the whole
book, fixes a glossary, and then translates under it. The form is a local CLI
plus a thin local API for the owner's own use (choosing a preset and starting a
run), with resumable runs, an adjustable prompt and glossary, and subscription
CLIs by default (paid API only with explicit consent). What the mission depends
on is Trunk: EPUB in and out, glossary extraction and injection, checkpoint
resume, the prompt, the paid gate, and the subscription runtimes. Its non-goals
feed `north_star_conflict`: a general translation platform, web or document
translation plugins, opening the local API to other products, silently
switching models or truncating or rewriting source text, and unbounded paid
retries.

The owner's global `PERSONAL-REPO-AUTOMATION.md` defines Door (Two-way /
One-way), Radius (Leaf / Branch / Trunk), Structure, the controlled-Branch
evidence, and the execution gates. This file maps those terms onto BookWeaver
and sets the review depth for each class.

Classify each change on three separate axes:

1. **Door:** can the change and its effects be undone?
2. **Radius:** if the change is wrong, how far does the failure spread?
3. **Structure:** does the change touch a structure path (below)? The changed
   file paths decide this, not judgment.

Keep Radius and Structure apart. BookWeaver's most expensive failures are
_wrong but green_: a change passes every test but silently invalidates saved
work. Examples: a new prompt sentence stops every unfinished book from
resuming, or a segmenter change maps saved translations to the wrong
paragraphs. The Structure gate exists to make those changes visible, whatever
their radius.

## Structure paths

The current application path uses no database (the legacy SQLite table
`quota_usage` below has no code reader or writer now). Its persistent structures are files that outlive
one run and that later runs, other books, or the owner's machine read back. A
change that adds, modifies or deletes anything under these paths has
**Structure = touched**:

- **Checkpoint schema and compatibility identity:** `ai/checkpoint_store.py`
  (`CheckpointIdentity`, `SegmentRecord`, schema version 2, the legacy v1 import
  and its provenance values).
- **Inputs to the checkpoint identity.** A change to the values these produce
  changes whether existing checkpoints resume:
  - The source signatures and the checkpoint location, in the helpers that the
    current path calls from the lower half of `ai/orchestration.py`:
    `_compute_content_signature` (the hard identity field `input_signature`,
    also the glossary cache `source`), `_compute_input_signature` (matched by the
    v1 import), `_resolve_checkpoint_dir` and `_CHECKPOINT_ROOT`. A renamed
    checkpoint directory silently starts every book fresh.
  - The EPUB system prompt: `ai/prompt_preparation.py` (`_SYSTEM_PROMPT_TEMPLATE`,
    `build_system_prompt`, `render`). Its SHA-256 becomes
    `CheckpointIdentity.system_prompt_hash` (`ai/orchestration.py:374`). The
    field is a soft identity field (not in the hard tuple at
    `ai/checkpoint_store.py:215`), so after a change, existing checkpoints resume
    only with `--force-resume`.
  - The glossary block that `render` puts into that prompt:
    `GlossaryManager.format_block` and `_priority_rank` in `ai/core/glossary.py`,
    and `GlossaryInjector.format_block` in `ai/glossary_injector.py`.
  - Segmenter output and its signature: `ai/epub_package.py`,
    `ai/adapters/sources/epub_adapter.py`, and `_ACTIVE_EPUB_SEGMENTER_SIGNATURE`
    in `ai/orchestration.py`. Checkpoints are keyed by segment ID, and
    `CheckpointStore.load` rejects unknown IDs.
  - The batch bounds and protocol name written into the identity in
    `ai/orchestration.py:251-265`: `batch_chars` (from
    `_resolve_default_batch_chars`, `_resolve_positive_int_config` and
    `_DEFAULT_BATCH_CHARS_*_EPUB`),
    `SEPARATOR_OVERHEAD` (derived from `_BATCH_SEPARATOR` in
    `ai/adapters/providers/_delimiter.py`), `max_batch_segments`, and
    `"segment_tags"`. Also `ai/core/batcher.py`.
  - The `profile` and `effort` values that `ai/model_profiles.py` resolves.
  - CLI defaults that become identity values: `--output-lang` (`output_lang` and
    the prompt language) and `--model` (`profile`) in `ai/cli.py`.
- **Glossary cache identity and format:** `glossary_cache_path` in
  `ai/term_extraction.py` (`.bookweaver_glossaries/<sha256>.json`, keyed on
  source signature, `mode`, `max_terms`, `model_id`, `effort` and
  `extractor_version: 1`). Its inputs include the
  mode precedence in `plan_glossary` (`ai/term_extraction.py`) and every `model_id`
  in `_CLI_PRESETS` and `_API_MODELS`: a model-ID-only change makes every cache
  miss, and the next run re-extracts. The file format is written by
  `ai/glossary_extractor.py` and read by `_validate_glossary_payload` and
  `_load_glossary_json_file` in `ai/core/glossary.py`. The cached glossary
  feeds the rendered prompt, so it also feeds `system_prompt_hash`.
- **Term Panel cache identity and files** (SPEC-028 §3.7): `panel_identity` and
  `plan_panel` in `ai/term_panel.py` (`plan_panel` builds
  `.bookweaver_glossaries/panel/<sha256>/` under the book folder, beside the EPUB for `--term-panel`, holding `glossary.json`, `term-panel-report.json` and
  `replies/`), and `panel_term_limits` in `ai/term_extraction.py`, which
  `bookweaver terms` and `--term-panel` share so both find one cache. The
  glossary it writes feeds `system_prompt_hash` like any supplied glossary.
- **Runtime configuration schema:** `ai/config_schema.json`,
  `ai/runtime_config.py`, `ai/core/config.py` (`_deep_merge`, which decides how
  the configuration files merge), and `config/config.json.example`. It
  includes `terminology_panels` and `runtimes.disabled` (SPEC-028 §3.10, §3.12). The owner's
  ignored `config/config.json` and `~/.config/bookweaver/config.json` must still
  validate. `AGENTS.md` forbids rewriting them automatically.
- **Runtime-certification store:** `$XDG_STATE_HOME/bookweaver/runtime-certifications.json`
  (`default_certification_path` and its entry format `_ENTRY_KEYS` in
  `ai/adapters/providers/subscription_cli_provider.py`), plus the seeded `CERTIFIED_AGY_MODELS` in
  `ai/model_profiles.py`.
- **Run artifacts:** the invocation audit (`.bookweaver_runs/<run_id>.json`,
  `persist_audit` in `ai/runtime_factory.py`; its fields, including `term_panel`,
  are written in `TranslationOrchestrator.translate`), the checkpoint `paid_usage_by_run`
  field, `warnings.json` / `<output>.warnings.json` (`ai/orchestration.py:430`), and `term-consistency.json` / `<output>.term-consistency.json` (`_report_term_usage` in `ai/orchestration.py`).
- **Local API run record and child log** (SPEC-026 §7.3): `$XDG_STATE_HOME/bookweaver/current-run.json`
  (`RunRecord` in `ai/local_api.py`, schema version 2), its lock file
  `current-run.lock`, and
  `<output directory>/.bookweaver_runs/<run_id>.log`.
- **Local API book library** (SPEC-026 §7.5): `~/Documents/BookWeaver/<book name>/`
  (`default_library_dir` in `ai/local_api.py`), which holds uploaded books. A resume
  depends on the stored copy.
- **Architecture decision records:** `docs/architecture/decisions/`. A new ADR records
  a significant decision reason and needs the owner's approval
  (`~/Documents/global-skills/agents/DOC-LIFECYCLE.md`, "Task closeout").
- **EPUB output format:** the bilingual EPUB that `ai/epub_package.py` writes is
  the product the owner keeps and reads in other apps.
- **Legacy stores:** the model probe cache `~/.cache/bookweaver/model_probe_cache.json`
  and the SQLite table `quota_usage`. No code reads or writes them since the legacy
  retirement (issue 21); files on disk are left alone.

Structure = touched means:

- The change must match a design the owner approved before implementation. The
  design names each structure it adds or alters: each new or changed identity
  field, each record field, each file format, and how existing files are
  handled (resume, hard mismatch, soft mismatch, or import). Anything not named
  there stops and waits for the owner's decision.
- The PR attaches evidence that existing files still behave as the design says.
  Example: an existing schema-v2 checkpoint fixture loads, or fails with the
  expected mismatch error.
- A change that makes existing checkpoints, glossary caches or certifications
  unusable without a recovery path is also One-way for the owner's unfinished
  books (see One-way effects).

Add a path here when the project gains another persistent structure.

## Radius in this repository

Radius answers only how far a failure spreads. Module boundaries come from
`tach.toml`. The current application path is `ai/cli.py` and `ai/local_api.py`,
then `ai/orchestration.py` (`TranslationOrchestrator`), then the runtime,
checkpoint, prompt and source modules it depends on.

| Radius | In this repository |
| --- | --- |
| **Trunk** | **Application composition:** `ai/orchestration.py` as a whole: `TranslationOrchestrator` and `translate_epub` (lines 173-588), the module-level imports (a broken import breaks every command), and the current-path helpers in the lower half listed under Structure paths. `ai/cli.py` reaches every translation through it, and `ai/local_api.py` reads the presets, counts segments and resolves the checkpoint directory through it. tach lists 10 dependencies for it, all of them enforced modules. **Checkpoint and resume:** `ai/checkpoint_store.py` and the identity inputs listed under Structure paths. Every book's resume depends on them. **Glossary extraction and injection** (the North Star's core difficulty): `ai/glossary_extractor.py`, `ai/term_extraction.py` (which glossary a run uses, its cache key and the reuse rule), `ai/term_panel.py` and `ai/core/term_panel.py` (the Term Panel runner and its vote rules), `ai/core/glossary.py`, `ai/core/index_signal_scorer.py`, `ai/core/local_glossary_candidates.py` and `ai/glossary_injector.py`. A worse term selection passes every test but lowers the quality the mission depends on. **Prompt:** `ai/prompt_preparation.py`. Every EPUB request carries this prompt, and its hash decides whether existing checkpoints resume. A prompt change also trips the golden-bytes test in `tests/unit/test_prompt_preparation.py`. **Paid-API gate and runtime selection:** `ai/runtime_factory.py` (authorization, the any-llm adapter, the usage audit), `is_metered` and `METERED_PROVIDERS` in `ai/model_profiles.py`, and their call sites in `ai/orchestration.py`. A wrong value can start a paid call. **Model registry:** `ai/model_profiles.py` (`_CLI_PRESETS`, `_API_MODELS`, `resolve_profile`, `CERTIFIED_AGY_MODELS`, and `refuse_disabled_runtime`, which stops a run on a disabled runtime). The CLI, the local API, the runtime factory and the checkpoint identity read it. **Transport framing:** `ai/adapters/providers/_delimiter.py` (`segment_tags`, `augment_prompt_for_batch`, response parsing). Every batch on every provider is framed and parsed here, and a parse error can misalign translations. **Subscription CLI runtime:** `ai/adapters/providers/subscription_cli_provider.py`, the shared adapter with the version gate, and `ai/adapters/providers/antigravity_provider.py`, the default runtime spec for every subscription run. **Translation engine core:** `ai/core/engine.py`, `ai/core/batcher.py`, and the ports in `ai/ports/`. Every adapter depends on the ports (tach `ai.ports`). **EPUB package handling:** `ai/epub_package.py`. Reading, segmentation and writing for every EPUB, plus glossary extraction (tach: `ai.adapters`, `ai.glossary_extractor`). **Runtime configuration:** `ai/runtime_config.py`, `ai/config_schema.json`, `ai/core/config.py`. **Dependencies and build:** `pyproject.toml` dependency bounds, the Python baseline, and major upgrades in `uv.lock`. The CLI wheel and `scripts/verify_installed_runtime.py` depend on them. **Boundaries:** `tach.toml`. |
| **Branch** | **CLI argument handling** in `ai/cli.py` behind an unchanged `orchestration` contract: help text, `presets` output formatting, or a new flag. Consumers: the owner and scripts that call the CLI. Containment: tach allows `ai.cli` to depend only on `ai.orchestration` and `ai.local_api`. A changed default is not Branch: `--output-lang` and `--model` defaults are identity inputs (Structure), and the `--provider`, `--allow-paid-api` and `--resume` defaults reach the paid gate or resume (Trunk). **Local API endpoints** in `ai/local_api.py` that only read registry data (`GET /presets`, filtered by `runtimes.disabled`, which `create_app` reads once from the runtime configuration; an invalid configuration stops `serve` at start), for the owner's own use; an endpoint meant for other products is a North Star non-goal. Containment: imported lazily, only by `serve`; bound to `127.0.0.1`. An endpoint that reads book text or checkpoints is Branch only after Host-header and cross-origin protection exists, because a DNS-rebinding page can read `127.0.0.1`; without it, Unknown. An endpoint that starts a run or accepts `allow_paid_api` (`POST /runs`) is Trunk (it reaches the paid gate). `GET /runs/current` and `POST /runs/current/stop` read the run record and signal the child; they are Trunk as part of the same run-control path. **Source adapters:** `ai/adapters/sources/epub_adapter.py` is the only one and it is not Branch, because its segment IDs are checkpoint keys. **Sanity probe heuristics** (`_SanityProbeConfig` and the CJK checks in `ai/orchestration.py:615-855`), when the warning file format stays unchanged. |
| **Leaf** | Test additions under `tests/` that leave existing assertions, fixtures and thresholds unchanged. Documentation that states no rule and backs no decision: `README.md`, design and implementation plans under `docs/plans/`, and typo or link fixes outside specs, `AGENTS.md`, `GLOSSARY.md` and `docs/agents/`. Evidence records under `docs/plans/` are Always stop (below). |

Not yet mapped, so treat these as **Unknown** and name the missing evidence in
the PR:

- **Remaining legacy files:** `benchmark_models.py` and `ai/gemini_provider.py`
  (they read the `page*.md` chunks of the retired PDF path and no longer run; kept
  until an EPUB-based benchmark replaces them), and the committed
  `glossary_auto.json` (no runtime reader found by search). Deleting them is an
  owner decision. `08_epub_roundtrip_baseline.py` is an evaluation asset (Always
  stop).
- `config/prompts/`: no code references it by path, and both files contain the
  `START`/`END` markers that `PromptPreparation.from_config` rejects for EPUB.
  A user configuration may still name one as a template.
- Minor-version upgrades in `uv.lock` (major upgrades are Trunk).
- Any path this table does not name.

## One-way effects in this repository

- **Real paid API calls** through a metered provider (`gemini`, `openai`,
  `anthropic`). Money spent does not come back. This includes the extraction
  call that a run may make on another preset.
- **Subscription quota spent** on Antigravity, Codex or Claude Code runs. A
  whole-book run cannot be undone. Live probes need separate authorization
  (`AGENTS.md`).
- **Invalidating the owner's unfinished checkpoints or glossary caches** without
  a recovery path. Retranslation costs quota, money or time, and the new text can
  differ in voice and terminology. A soft identity change (such as
  `system_prompt_hash`) can be recovered with `--force-resume`, at the cost of
  mixed prompts in one book. A hard identity change (`input_signature`,
  `input_format`, `segmenter_signature`) cannot.
- **Rewriting or deleting files outside the repository:** the owner's
  `~/.config/bookweaver/config.json`, the runtime-certification store,
  checkpoints under an output directory, and finished EPUBs.
- **Upgrading a persisted format in place** (checkpoint, certification store)
  so that an older BookWeaver can no longer read it.

## Always stop, whatever the class

- **Verifier changes:**
  - `.github/workflows/`;
  - `scripts/verify_installed_runtime.py`, `scripts/check_doc_links.py` and
    `scripts/probe_antigravity_version.py`
    (the documented tool to run before seeding a version);
  - the verification commands in `AGENTS.md`;
  - the `[tool.ruff]` rules in `pyproject.toml`, and `tach.toml` rules or exclusions;
  - existing test assertions, fixtures (`tests/fixtures/`, `tests/runtime_fakes.py`,
    `tests/conftest.py`), thresholds, skips and golden values;
  - the sanity-probe thresholds when a change only makes a failing book pass.

  Adding coverage for an approved behavior change is not a verifier change.
  Weakening or removing a check is.
- **Evaluation, baseline and evidence records:** `08_epub_roundtrip_baseline.py`,
  the evaluation specs (SPEC-004, SPEC-005) and their plans, and the evidence
  records under `docs/plans/` that back a default, a seed or a quality claim:
  the A/B and batch-size reports (`2026-04-03-*`), the book-validation and
  protocol-probe records (`2026-09-07-*`), and the compatibility probe
  (`2026-11-07-antigravity-1.5.3-compatibility-probe.md`, cited by
  `ai/model_profiles.py`). Editorial provenance must stay separate (`AGENTS.md`).
- **Paid-API gating:** `ai/runtime_factory.py` authorization, `--allow-paid-api`
  and the `USE_API` prompt, `is_metered` / `METERED_PROVIDERS`, and any API
  field that grants paid consent. This is also Trunk.
- **The Antigravity version gate:** `CERTIFIED_AGY_MODELS` and the probe pass
  criteria (`probe_problems` and `PROBE_SAMPLES` in `ai/adapters/providers/subscription_cli_provider.py`). Seeding a new
  pair needs probe evidence.
- **Policy text:** `AGENTS.md`, `GLOSSARY.md`, `docs/agents/`, and approved specs
  under `docs/architecture/specs/`; ADRs under `docs/architecture/decisions/`.

## Review depth

| Classification | Delivery and review | Owner involvement |
| --- | --- | --- |
| Leaf, Two-way, Structure untouched | One implementation; L1 review: same-vendor Standards and Spec, plus Risk on the vendor that did not author the change (policy "Review tiers"); then merge | None, once automatic merge prerequisites hold |
| Controlled Branch, Two-way, Structure untouched | The author records consumers and failure propagation; the L1 review (as above) verifies that evidence. A Branch without that evidence is not controlled and stops (`risk_not_low`) | Only when author and reviewer disagree |
| Structure touched, within the approved design | Independent review, plus evidence that existing checkpoints, caches or configuration behave as the design says | Design approval before work; at merge, only when the review finds a difference from the design |
| Trunk, One-way, Unknown, Structure outside the design, or an "Always stop" item | Owner design approval before implementation; independent review plus L2 cross-vendor review (Codex for Claude Code's work). For runtime changes, evidence from a real run when the owner authorizes one; mocked tests alone are not proof of book quality (`AGENTS.md`) | Design approval before work, decision before merge |

The coordinator runs the independent reviewer itself and gives it only the
requirement text, the pinned base and head, and the code. A Risk request also
gets the PR's Merge Danger section and the task's link and full text
(`RISK-REVIEW.md`); a missing Merge Danger counts as `risk_disagreement`. The coordinator
verifies each finding and brings the owner only the decisions in the last two
rows or a disagreement.

## Slicing example: SPEC-026 Phase 3, starting runs from the local API

Phase 3 adds `POST /runs`, `GET /runs/current` and `POST /runs/current/stop`.
The run happens in a child process (`bookweaver <source> --output <output> --preset <name>`).
It splits like this:

1. **Design gate (the owner approves).** The design names:
   - where the child-process log lives;
   - whether a run record file lets `serve` find the current run after a
     restart, and its exact fields;
   - how status reads the checkpoint (planned versus done counts);
   - the Host-header and cross-site POST protection;
   - the non-terminal stdin, so the paid gate rejects instead of prompting.

   The log and the run record are new persistent structures, so the design
   names their formats, and this map adds their paths.
2. **Trunk ticket.** Host-header and cross-origin protection for the whole
   API, then `POST /runs`, which starts a child process that can reach the paid
   gate. The tests prove that a metered preset without `allow_paid_api` is
   rejected, and that a cross-origin or foreign-Host request is refused. Owner
   decision before merge.
3. **Structure ticket, within the design.** The run record and log writer, at
   the paths and formats the design named. Review plus fixture evidence.
4. **Branch ticket, Structure untouched, after tickets 2 and 3.**
   `GET /runs/current` reads the run record and the existing checkpoint document
   without changing `ai/checkpoint_store.py`. It reads book-derived state, so it
   relies on the protection from ticket 2. Review, then merge.
5. **Unknown ticket until the design classifies it.** `POST /runs/current/stop`
   signals the child process. It changes state, and stopping a metered run loses
   a batch that is already paid for. This map has no class for an endpoint that
   controls a process, so it stops for the owner.
6. **Stops.** Adding a progress field to `checkpoint.json` changes the checkpoint
   schema: it needs its own design approval. Any live run to demonstrate Phase 3
   spends quota (One-way) and needs separate authorization.

## Prerequisites before automatic merge

As of 2026-11-08, none of these holds, so automatic merge stays off:

- **`main` requires the `lint-and-test` checks** (`lint` and `test` jobs in
  `.github/workflows/lint.yml`). Today `main` has no ruleset, so nothing blocks
  a merge on a failing check.
- **Agents and the owner have different GitHub identities.** PRs are opened and
  merged as the owner's account. `lint.yml` runs from the PR itself, so a PR can
  change the check that judges it. Until agents act through a separate account
  or GitHub App and CODEOWNERS covers the paths below, agents follow the verifier
  and Structure rules. GitHub does not enforce them.
- **A rule the PR cannot change checks the Structure and Always-stop paths.**
  Example: a required check, defined outside the PR's own workflow, that fails
  when a listed path changes without an owner label.
