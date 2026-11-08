---
specId: SPEC-026
title: Named Rows and a Local API over the Existing Application Path
status: Approved for implementation (2026-11-07)
implementationStatus: Phase 1 implemented (2026-11-07), awaiting the owner's real-run checkpoint; Phases 2-4 not started
priority: P2 - Usability
creationDate: 2026-11-07
lastUpdateDate: 2026-11-07
owner: User (AI-Assisted)
relatedSpecs: [SPEC-020, SPEC-021, SPEC-024, SPEC-025]
tags:
  - ui
  - local-api
  - local-only
  - runtime-selection
---

# SPEC-026: Named Rows and a Local API over the Existing Application Path

## 1. Goal

Reduce how much the owner must think about and remember to start a correct run. A good-looking UI is not a goal. BookWeaver is a command line tool plus a thin local API; both read the same named rows.

The main reducer is the named-row registry (SPEC-025 §3.8) plus `--row` and a `bookweaver rows` listing. The local API and its generated `/docs` page are in scope (owner decision 2026-11-07): they show types, defaults and choices without reading help text, and give agents and scripts a typed entry point.

The rows cover every runtime kind, so the API starts runs on both:

- subscription CLI rows (Antigravity, Codex, Claude Code);
- metered API rows (Gemini, Anthropic, OpenAI), under the paid-API consent rule (§4.2 step 4).

The number of choices is growing: runtimes, quota pools, tiers, efforts and their evidence layers (SPEC-025 §3.8). Remembering CLI flags for each named row does not scale. The UI shows the enabled rows and their evidence, and starts one run.

## 2. Owner decisions (2026-11-07)

| Question | Decision |
|---|---|
| Main purpose | Choose a book and an enabled combination row, then start the run |
| Access | This Mac only (`127.0.0.1`) |
| Concurrency | One book at a time |

Not requested now: run monitoring beyond basic status, human review of translations, reading or downloading finished books. Each is a separate decision later.

### 2.1 UI = the generated OpenAPI page (owner direction 2026-11-07)

No custom front end. A small FastAPI app exposes typed endpoints; FastAPI generates the OpenAPI schema and the interactive Swagger UI at `/docs`. That page is the UI.

Why this is enough:

- The request model is the parameter documentation. Each field has a type, a description and a default; the owner does not need to remember CLI flags.
- The enabled rows are an `Enum` in the request model, so `/docs` shows them as a dropdown. A combination outside the registry cannot be sent.
- Validation happens before anything runs, through Pydantic and the same resolver the CLI uses. Errors come back as structured 422 or 400 responses.
- The same schema is machine-readable, so an agent (Claude Code, Codex) can call the API without a hand-written wrapper.

Lesson from the local-asr-service `/docs` page: its `model` field is `string | null`, and the valid aliases and their rules (Deepgram needs `en` or `zh`, `auto` is invalid there, MOSS needs `en` and at most 30 minutes) live in long description prose. The page works, but the owner must read a manual to fill one form. BookWeaver puts those rules in types instead:

- `row` is an Enum, never a free string. Each row already fixes runtime, tier, family and effort, so no per-model prose rule is needed.
- A rule that cannot be a type is enforced by the server and returned as an error. It is not only described in text.
- Field descriptions stay one sentence. If a field needs a paragraph, the model of the request is wrong.

What the page does not give, accepted for this scope:

- No file picker: EPUB and output paths are typed as text.
- No live progress view: the owner calls the status endpoint again to refresh it.

### 2.2 Shorter CLI as a side effect

Once SPEC-025 rows have names, the CLI accepts `--row <name>` in place of the separate runtime, tier and effort flags. The long command line becomes `bookweaver book.epub --output out.epub --row agy-flash-low`. Both entry points resolve the same row.

## 3. Design constraints

Source principles: research notes `2026-10-28_tech-engineering_build-vs-adopt-in-the-ai-era` (the local ASR service drifted into a general gateway) and `2026-10-08_puresubs_poc-to-complexity-explosion-retrospective` (parallel state grew around the core task).

- **The UI is another entry point, not a new system.** It builds the same typed options the CLI builds and calls the same application path.
- **The checkpoint stays the only run state.** No job table, no queue, no second progress store. Status is read from the checkpoint and the run process.
- **One run at a time** is already enforced by the checkpoint's exclusive run lock. The UI does not add its own lock.
- **No long-lived service.** `uv run bookweaver serve` starts the local API on demand; stopping it does not stop a translation that is running.
- **Paid rows keep their consent rule.** A metered row (SPEC-020, SPEC-024) needs an explicit per-run confirmation in the UI that shows the provider, model and the paid-API warning text the CLI prints. No stored "always allow".

## 4. Behavior

### 4.1 Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /rows` | Enabled rows with runtime (quota pool), tier, family, effort, status (`default`, `manual`, `experiment`) and highest proven layer |
| `POST /runs` | Start one run. Body: `source`, `output`, `row` (Enum), optional prompt and glossary fields, `allow_paid_api` (default false). Returns `202` with the run's checkpoint path |
| `GET /runs/current` | Basic status (§4.2) |
| `POST /runs/current/stop` | Send the same signal as Ctrl-C to the child process |

### 4.2 Start a run

1. The owner reads `GET /rows` in `/docs`, then fills `POST /runs`. The `row` field is a dropdown of enabled rows only.
2. The server validates the body with the same resolver the CLI uses. Validation errors are returned as they are, without reinterpretation.
3. The server starts the run as a child process: `bookweaver <source> --output <output> --row <name>`. Reasons for a child process instead of an in-process call:
   - the run survives a closed browser tab and a stopped UI server;
   - stopping a run is a process signal with the same semantics as Ctrl-C today;
   - the CLI stays the single tested contract.

4. A metered row with `allow_paid_api` false is rejected with the same paid-API warning text the CLI prints. The flag is per request; nothing is stored.

### 4.3 Basic status (minimum needed to know the run started)

- Running / finished / failed, from the child process and the checkpoint.
- Segments done versus planned, from the checkpoint.
- The last lines of the run's own log output.

Richer monitoring is out of scope (§2).

## 5. Out of scope

- LAN or phone access, login, multi-user.
- Queues or parallel runs, including parallel runs on different quota pools.
- Side-by-side human review and AI-judge screens (SPEC-025 §3.7; separate evaluation spec).
- A general job framework. If queues or scheduling are ever needed, adopt a library instead of extending this API.

## 6. Open items

- [ ] Add FastAPI and uvicorn as an optional dependency group (`uv add --optional ui ...`) so the CLI install stays lean.
- [ ] Confirm that the checkpoint exposes planned versus done counts without loading all segment text.
- [ ] Decide where the child process log is written so the UI can tail it after a restart.

## 7. Phases

1. `--row <name>` and `bookweaver rows` on the CLI. Depends on SPEC-025 Phase 1 registry. **Checkpoint:** the owner uses the short command on a real run and confirms the row names and listing before the API is built on them.
2. `GET /rows`, including both subscription CLI rows and metered API rows.
3. `POST /runs`, status and stop, through a child process.
4. Metered API rows through `POST /runs`: rejection without `allow_paid_api`, with offline tests that no metered row can start without it. No live paid call is part of this phase.

### 7.1 Phase 1 as built (2026-11-07)

- Row names: `<runtime>-<tier>-<effort>` for subscription CLI rows (`agy-flash-low`), `<provider>-<tier>` for metered rows (`gemini-flash`, `anthropic-pro`). Metered rows have no effort part because the vendor effort is pinned in `ai/model_profiles.py`.
- `ai/model_profiles.py` derives the rows (`enabled_rows()`, `find_row()`) from `_CLI_ROWS` and `_API_MODELS`, so there is no second list to keep in sync. Entry points reach them through `ai.orchestration`, which keeps the tach rule that `ai.cli` depends only on the application boundary.
- `bookweaver rows` prints a table; `bookweaver rows --json` prints the same fields for scripts and agents.
- `--row NAME` sets provider, tier and effort. Combining it with `--model`, `--effort` or `--provider` (abbreviations included) is an error. The separate flags remain for now.
- A metered row does not imply consent. It uses the same paid gate as `--provider`: `--allow-paid-api`, or typing `USE_API` at the interactive prompt; a non-interactive run without the flag fails. Its evidence text says so in both the table and the JSON.
- Metered rows show no evidence layer: they have offline contract tests only (SPEC-024) and no live probe, so they do not claim Layer 2 executability.
- `bookweaver rows` is a reserved first argument. A source literally named `rows` must be passed as `./rows`.
- Checkpoint identity is unchanged: `--row agy-flash-low` resolves to the same profile and effective effort as the default command, so existing checkpoints resume. Only the recorded requested effort differs (`low` instead of none).

## 8. Verification

- Offline tests at the HTTP boundary with a fake `bookweaver` child process: argument derivation per row, rejection of rows not in the registry, paid-row consent, status read from a fixture checkpoint.
- The server binds to `127.0.0.1` only; a test asserts this.
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`, `uv run tach check`.
