# Impact radius map

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

BookWeaver has no database. Its persistent structures are files that outlive
one run and that later runs, other books, or the owner's machine read back. A
change that adds, modifies or deletes anything under these paths has
**Structure = touched**:

- **Checkpoint schema and compatibility identity:** `ai/checkpoint_store.py`
  (`CheckpointIdentity`, `SegmentRecord`, schema version 2, the legacy v1 import
  and its provenance values).
- **Inputs to the checkpoint identity.** A change to the values these produce
  changes whether existing checkpoints resume:
  - The EPUB system prompt: `ai/prompt_preparation.py` (`_SYSTEM_PROMPT_TEMPLATE`,
    `build_system_prompt`, `render`). Its SHA-256 becomes
    `CheckpointIdentity.system_prompt_hash` (`ai/orchestration.py:368`).
  - `config/prompts/` (prompt templates that `render` can use instead).
  - Segmenter output and its signature: `ai/epub_package.py`,
    `ai/adapters/sources/epub_adapter.py`, and `_ACTIVE_EPUB_SEGMENTER_SIGNATURE`
    in `ai/orchestration.py`. Checkpoints are keyed by segment ID, and
    `CheckpointStore.load` rejects unknown IDs.
  - The batch bounds and protocol name written into the identity in
    `ai/orchestration.py:240-252` (`batch_chars`, `SEPARATOR_OVERHEAD`,
    `max_batch_segments`, `"segment_tags"`), and `ai/core/batcher.py`.
  - The `profile` and `effort` values that `ai/model_profiles.py` resolves.
- **Glossary cache identity:** `glossary_cache_path` in
  `ai/prompt_preparation.py` (`.bookweaver_glossaries/<sha256>.json`, with
  `extractor_version: 1`) and the glossary JSON format in `ai/glossary_extractor.py`
  and `config/schemas/glossary_schema.json`. The cached glossary feeds the
  rendered prompt, so it also feeds `system_prompt_hash`.
- **Runtime configuration schema:** `ai/config_schema.json`,
  `ai/runtime_config.py`, and `config/config.json.example`. The owner's ignored
  `config/config.json` and `~/.config/bookweaver/config.json` must still
  validate. `AGENTS.md` forbids rewriting them automatically.
- **Runtime-certification store:** `$XDG_STATE_HOME/bookweaver/runtime-certifications.json`
  (`default_certification_path` and its entry format `_ENTRY_KEYS` in
  `ai/antigravity_provider.py`), plus the seeded `CERTIFIED_AGY_MODELS` in
  `ai/model_profiles.py`.
- **Run artifacts:** the invocation audit (`.bookweaver_runs/<run_id>.json`,
  `persist_audit` in `ai/runtime_factory.py`), the checkpoint `paid_usage_by_run`
  field, and `warnings.json` / `<output>.warnings.json` (`ai/orchestration.py:424`).
- **EPUB output format:** the bilingual EPUB that `ai/epub_package.py` writes is
  the product the owner keeps and reads in other apps.

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

Add a path here when the project gains another persistent structure. Example:
the SPEC-026 Phase 3 run record or child-process log that lets `serve` find the
current run after a restart.

## Radius in this repository

Radius answers only how far a failure spreads. Module boundaries come from
`tach.toml`. The current application path is `ai/cli.py` and `ai/local_api.py`,
then `ai/orchestration.py` (`TranslationOrchestrator`), then the runtime,
checkpoint, prompt and source modules it depends on.

| Radius | In this repository |
| --- | --- |
| **Trunk** | **Application composition:** `TranslationOrchestrator` and `translate_epub` / `translate_markdown` / `translate_pdf` in `ai/orchestration.py:146-540`. Every entry point (`ai/cli.py`, `ai/local_api.py`) reaches every format through it, and it depends on 11 tach modules. **Checkpoint and resume:** `ai/checkpoint_store.py` and the identity inputs listed under Structure paths. Every book's resume depends on them. **Prompt:** `ai/prompt_preparation.py` and `config/prompts/`. Every EPUB request carries this prompt, and its hash decides whether existing checkpoints resume. **Paid-API gate and runtime selection:** `ai/runtime_factory.py` (authorization, the any-llm adapter, the usage audit), `is_metered` and `METERED_PROVIDERS` in `ai/model_profiles.py`, and their call sites in `ai/orchestration.py`. A wrong value can start a paid call. **Model registry:** `ai/model_profiles.py` (`_CLI_ROWS`, `_API_MODELS`, `resolve_profile`, `CERTIFIED_AGY_MODELS`). The CLI, the local API, the runtime factory and the checkpoint identity read it. **Transport framing:** `ai/adapters/providers/_delimiter.py` (`segment_tags`, `augment_prompt_for_batch`, response parsing). Every batch on every provider is framed and parsed here, and a parse error can misalign translations. **Antigravity runtime:** `ai/antigravity_provider.py`, the default runtime for every subscription run, and its version gate. **Translation engine core:** `ai/core/engine.py`, `ai/core/batcher.py`, and the ports in `ai/ports/`. Every adapter depends on the ports (tach `ai.ports`). **EPUB package handling:** `ai/epub_package.py`. Reading, segmentation and writing for every EPUB, plus glossary extraction (tach: `ai.adapters`, `ai.glossary_extractor`). **Runtime configuration:** `ai/runtime_config.py`, `ai/config_schema.json`, `ai/core/config.py`. **Dependencies and build:** `pyproject.toml` dependency bounds, the Python baseline, and major upgrades in `uv.lock`. The CLI wheel and `scripts/verify_installed_runtime.py` depend on them. **Boundaries:** `tach.toml`. |
| **Branch** | **CLI argument handling** in `ai/cli.py` behind an unchanged `orchestration` contract: one flag, its help text, or `rows` output formatting. Consumers: the owner and scripts that call the CLI. Containment: tach allows `ai.cli` to depend only on `ai.orchestration` and `ai.local_api`. **Local API endpoints** in `ai/local_api.py` that only read (today `GET /rows`). Containment: imported lazily, only by `serve`; bound to `127.0.0.1`. An endpoint that starts a run or accepts `allow_paid_api` is Trunk (it reaches the paid gate). **One isolated source adapter** behind an unchanged `IBookSource` port: `ai/adapters/sources/markdown_adapter.py` or `ai/adapters/sources/pdf_adapter.py`, which run only with `--allow-isolated-format`. `epub_adapter.py` is not Branch, because its segment IDs are checkpoint keys. **Glossary extraction internals** (`ai/glossary_extractor.py`, `ai/glossary_injector.py`, `ai/core/glossary*.py`, `ai/core/index_signal_scorer.py`, `ai/core/local_glossary_candidates.py`), when the glossary JSON format, the cache identity and the rendered prompt block stay unchanged. **Sanity probe heuristics** (`_SanityProbeConfig` and the CJK checks in `ai/orchestration.py:574-815`), when the warning file format stays unchanged. |
| **Leaf** | Test additions under `tests/` that leave existing assertions, fixtures and thresholds unchanged. Documentation that states no rule: plans under `docs/plans/`, `README.md`, and typo or link fixes outside specs, `AGENTS.md`, `CONTEXT.md` and `docs/agents/`. `scripts/probe_antigravity_version.py`, run by hand and read by no module. It leaves the certification store untouched (`scripts/probe_antigravity_version.py:78`). |

Not yet mapped, so treat these as **Unknown** and name the missing evidence in
the PR:

- **Legacy code pending retirement** (`AGENTS.md`, "Migration status"):
  - the historical helpers in `ai/orchestration.py` from `CheckpointMetadata` (about line 832) down,
    including `resolve_model` and `create_provider`;
  - `ai/model_resolver.py`, `ai/model_probe.py` and `ai/provider_factory.py`,
    used by those helpers;
  - `ai/gemini_provider.py`, `ai/gemini_api_provider.py`,
    `ai/adapters/providers/gemini_*_adapter.py`, `ai/model_selector.py`,
    `ai/quota_tracker.py`, `ai/bilingual_merger.py` and the orphaned
    `ai/epub_translate_roundtrip.py`;
  - the root `0*_*.py` scripts, `translatebook.sh`, `benchmark_models.py`,
    `generate_test_epub.py` and `pipeline_utils.py`.

  Missing evidence: no complete consumer map exists. Legacy tests import some of
  these files (`tests/unit/test_translate_step3_refactor.py`,
  `tests/unit/test_epub_baseline_cli.py`). Deleting them is a retirement
  decision for the owner, not a Leaf cleanup. `08_epub_roundtrip_baseline.py`
  is an evaluation asset (Always stop).
- `CONTEXT.md` (it may state rules) and any path this table does not name.

## One-way effects in this repository

- **Real paid API calls** through a metered provider (`gemini`, `openai`,
  `anthropic`). Money spent does not come back. This includes the extraction
  call that a run may make on another row.
- **Subscription quota spent** on Antigravity, Codex or Claude Code runs. A
  whole-book run cannot be undone. Live probes need separate authorization
  (`AGENTS.md`).
- **Invalidating the owner's unfinished checkpoints or glossary caches** without
  a recovery path. Retranslation costs quota, money or time, and the new text can
  differ in voice and terminology. Example: a prompt or identity change merged
  while a book is half translated.
- **Rewriting or deleting files outside the repository:** the owner's
  `~/.config/bookweaver/config.json`, the runtime-certification store,
  checkpoints under an output directory, and finished EPUBs.
- **Upgrading a persisted format in place** (checkpoint, certification store)
  so that an older BookWeaver can no longer read it.

## Always stop, whatever the class

- **Verifier changes:**
  - `.github/workflows/`;
  - `scripts/verify_installed_runtime.py`;
  - the verification commands in `AGENTS.md`;
  - the `[tool.ruff]`, `[tool.pytest]` and `tach.toml` rules or exclusions;
  - existing test assertions, fixtures (`tests/fixtures/`, `tests/runtime_fakes.py`,
    `tests/conftest.py`), thresholds, skips and golden values;
  - the sanity-probe thresholds when a change only makes a failing book pass.

  Adding coverage for an approved behavior change is not a verifier change.
  Weakening or removing a check is.
- **Evaluation and baseline assets:** `08_epub_roundtrip_baseline.py`, the
  evaluation specs (SPEC-004, SPEC-005) and their plans, and the book-validation
  evidence under `docs/plans/` (`2026-09-07-*`). Editorial provenance must stay
  separate (`AGENTS.md`).
- **Paid-API gating:** `ai/runtime_factory.py` authorization, `--allow-paid-api`
  and the `USE_API` prompt, `is_metered` / `METERED_PROVIDERS`, and any API
  field that grants paid consent. This is also Trunk.
- **The Antigravity version gate:** `CERTIFIED_AGY_MODELS` and the probe pass
  criteria (`probe_problems` in `ai/antigravity_provider.py`). Seeding a new
  pair needs probe evidence.
- **Policy text:** `AGENTS.md`, `CONTEXT.md`, `docs/agents/`, and approved specs
  and ADRs under `docs/architecture/`.

## Review depth

| Classification | Delivery and review | Owner involvement |
| --- | --- | --- |
| Leaf, Two-way, Structure untouched | One implementation, one independent review (Standards, Spec, Risk), then merge | None, once automatic merge prerequisites hold |
| Controlled Branch, Two-way, Structure untouched | The author records consumers and failure propagation; the independent review verifies that evidence | Only when author and reviewer disagree |
| Structure touched, within the approved design | Independent review, plus evidence that existing checkpoints, caches or configuration behave as the design says | Design approval before work; at merge, only when the review finds a difference from the design |
| Trunk, One-way, Unknown, Structure outside the design, or an "Always stop" item | Owner design approval before implementation; independent review plus L2 cross-vendor review (Codex for Claude Code's work). For runtime changes, evidence from a real run when the owner authorizes one; mocked tests alone are not proof of book quality (`AGENTS.md`) | Design approval before work, decision before merge |

The coordinator runs the independent reviewer itself and gives it only the
requirement text, the pinned base and head, and the code. The coordinator
verifies each finding and brings the owner only the decisions in the last two
rows or a disagreement.

## Slicing example: SPEC-026 Phase 3, starting runs from the local API

Phase 3 adds `POST /runs`, `GET /runs/current` and `POST /runs/current/stop`.
The run happens in a child process (`bookweaver <source> --output <output> --row <name>`).
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
2. **Branch ticket, Structure untouched.** `GET /runs/current` reads the existing
   checkpoint document without changing `ai/checkpoint_store.py`. Independent
   review, then merge.
3. **Structure ticket, within the design.** The run record and log writer, at
   the paths and formats the design named. Review plus fixture evidence.
4. **Trunk ticket.** `POST /runs` starts a child process that can reach the paid
   gate. The tests prove that a metered row without `allow_paid_api` is
   rejected, and that a cross-origin request is refused. Owner decision before
   merge.
5. **Stops.** Adding a progress field to `checkpoint.json` changes the checkpoint
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
