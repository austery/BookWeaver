---
specId: SPEC-026
title: Named Rows and a Local API over the Existing Application Path
status: Approved for implementation (2026-11-07)
implementationStatus: Phases 1-4 implemented (Phase 4 on 2026-11-08); owner acceptance open: the first real run with `--row` or the API
priority: P2 - Usability
creationDate: 2026-11-07
lastUpdateDate: 2026-11-08
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
- **The checkpoint stays the only run state.** No job table, no queue, no second progress store. Status is read from the checkpoint and the run process. (§7.3 adds one small run record, so the server can find the current child and its planned segment count; it holds no translation progress.)
- **One run at a time.** The checkpoint's exclusive run lock covers one book. §7.3 adds the server-wide rule: `POST /runs` refuses a second run, on any book, while one runs.
- **No long-lived service.** `uv run bookweaver serve` starts the local API on demand; stopping it does not stop a translation that is running.
- **Paid rows keep their consent rule.** A metered row (SPEC-020, SPEC-024) needs an explicit per-run confirmation in the UI (`allow_paid_api`); a rejection names the provider and model and carries the CLI's paid-API text. No stored "always allow".

## 4. Behavior

### 4.1 Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /rows` | Enabled rows with runtime (quota pool), provider, tier, effort, concrete `model_id` (which names the family), status (`default`, `manual`, `experiment`), highest proven layer and evidence (§7.2) |
| `POST /runs` | Start one run. Body: `source`, `output`, `row` (Enum), optional prompt and glossary fields, `allow_paid_api` (default false). Returns `202` with the run's status, including its checkpoint directory |
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

- [x] Add FastAPI and uvicorn as the optional `api` extra so the CLI install stays lean; the dev group also carries them (plus httpx) so CI runs the HTTP tests (Phase 2).
- [x] Planned versus done counts: the checkpoint records only the done count (`translated_segment_count`). The server counts planned segments itself at start (§7.3 decision 3).
- [x] Child process log location (§7.3 decision 1).
- [x] Phase 3: start the child with a non-terminal stdin (§7.3 decision 5).

## 7. Phases

1. `--row <name>` and `bookweaver rows` on the CLI. Depends on SPEC-025 Phase 1 registry. **Checkpoint:** the owner uses the short command on a real run and confirms the row names and listing before the API is built on them.
2. `GET /rows`, including both subscription CLI rows and metered API rows.
3. `POST /runs`, status and stop, through a child process.
4. Metered API rows through `POST /runs`: rejection without `allow_paid_api`, with offline tests that no metered row can start without it. No live paid call is part of this phase.

### 7.1 Phase 1 as built (2026-11-07)

- Row names: `<runtime>-<tier>-<effort>` for subscription CLI rows (`agy-flash-low`), `<provider>-<tier>` for metered rows (`gemini-flash`, `anthropic-pro`). Metered rows have no effort part because the vendor effort is pinned in `ai/model_profiles.py`.
- `ai/model_profiles.py` derives the rows (`enabled_rows()`, `find_row()`) from `_CLI_ROWS` and `_API_MODELS`, so there is no second list to keep in sync. Entry points reach them through `ai.orchestration`, which keeps the tach rule that `ai.cli` depends only on the application boundary.
- `bookweaver rows` prints a table; `bookweaver rows --json` prints the same fields for scripts and agents. The table shows a missing effort or layer as `-`.
- `--row NAME` sets provider, tier and effort. Combining it with `--model`, `--effort` or `--provider` (abbreviations included) is an error. The separate flags remain for now.
- A metered row does not imply consent. It uses the same paid gate as `--provider`: `--allow-paid-api`, or typing `USE_API` at the interactive prompt; a non-interactive run without the flag fails. Its evidence text says so in both the table and the JSON.
- Metered rows show no evidence layer: they have offline contract tests only (SPEC-024) and no live probe, so they do not claim Layer 2 executability.
- `bookweaver rows` is a reserved first argument. A source literally named `rows` must be passed as `./rows`.
- Checkpoint identity is unchanged: `--row agy-flash-low` resolves to the same profile and effective effort as the default command, so existing checkpoints resume. Only the recorded requested effort differs (`low` instead of none).

Owner decision (2026-11-07): the Phase 1 real-run checkpoint is deferred because no book is waiting for translation; work continues to Phase 2. The first real run with `--row` still confirms the row names.

### 7.2 Phase 2 as built (2026-11-07)

- `uv run bookweaver serve [--port 8765]` starts the API in the foreground. The host is fixed at `127.0.0.1`; there is no host option. Like `rows`, `serve` is a reserved first argument; pass a source named `serve` as `./serve`.
- `GET /rows` returns the same objects as `bookweaver rows --json`. The OpenAPI page at `/docs` shows `runtime`, `provider`, `profile`, `effort`, `status` and `layer` as enums.
- Rows gained a `runtime` field: the quota pool (`antigravity`, or the metered vendor). `provider` alone cannot tell Codex and Claude Code rows apart once they exist. §4.1 originally listed `family`; it was dropped, and §4.1 amended, because `model_id` already names the concrete model.
- Known limit: FastAPI's `/docs` page loads Swagger UI from a CDN, so it renders blank without network. `GET /rows` and `/openapi.json` work offline. Accepted for now; self-hosting the assets is a later decision.
- `ai/local_api.py` depends only on `ai.orchestration` (tach). `ai.cli` imports it lazily, so an install without the `api` extra keeps working, and `serve` names the install command (`uv sync --extra api` in a checkout, `bookweaver[api]` for an installed package) instead of failing with a stack trace when either FastAPI or uvicorn is missing.

### 7.3 Phase 3 design and as built (owner-approved in chat, 2026-11-08)

The owner approved these six decisions before implementation. Each names the persistent files it adds, as the radius map's Structure gate requires (`docs/agents/impact-radius.md`).

1. **Child log.** The child's stdout and stderr go to `<output directory>/.bookweaver_runs/<run_id>.log`, beside the existing invocation audits. `run_id` is a new UUID the server generates per start; it is not the audit's run ID. The file is plain text, appended by the child, never rewritten by the server.
2. **Run record.** The server writes one file, `$XDG_STATE_HOME/bookweaver/current-run.json` (default `~/.local/state/bookweaver/`, the same root as the runtime-certification store), atomically. Fields, schema version 1:
   - `schema_version` (1), `run_id`;
   - `pid` (the child; it leads its own process group) and `process_start` (the child's start time exactly as `ps -o lstart=` prints it in the C locale); both `null` until the child exists;
   - `source`, `output` (absolute paths), `row`, `allow_paid_api`;
   - `started_at` (UTC ISO 8601), `log_path`, `checkpoint_dir`, `planned_segments`;
   - `exit_code` and `ended_at`: `null` until the server observes the child exit, then written once.

   A start writes the record twice: first without `pid` and `process_start`, before the child exists; then with them, right after it starts. A new start replaces the file. Nothing else writes it. When the server restarts while a child runs, it cannot observe the exit; status then reports `ended` with `exit_code: null` once the process is gone.

   **Lock.** An empty lock file, `current-run.lock` in the same directory, serializes starts and record updates across threads and across `serve` processes that share the state directory (`flock`), so two servers cannot start two runs.

   **Identity.** A process counts as this run's child only while its command line carries `<source> --output <output> --row <row>` and either:
   - its PID and `ps` start text both equal `pid` and `process_start` (a reused PID has a different start time, so it is never signalled); or
   - when the record has no `pid` yet (the server died between starting the child and recording it), it is the only such process and it started within 5 seconds of `started_at`, measured from `ps -o etime=` (elapsed time, so time zones and daylight saving do not matter).

   **Failures.** If the first write fails, nothing starts (500). If the second write fails, the server stops the child and returns 500, because an unrecorded run could not be watched or stopped. A record that is not valid JSON, not schema version 1, or has a missing, extra or wrongly typed field makes every run endpoint return 500 with the file path: whether a run is live is unknown, so the owner checks and deletes the file.
3. **Progress.** At start, the server segments the source EPUB once through the application path and stores the count as `planned_segments`. Done segments come from `translated_segment_count` in `<checkpoint_dir>/checkpoint.json`, read without the lock (the file is replaced atomically). The checkpoint format does not change.
4. **Request protection.** Every request must carry a `Host` of `127.0.0.1` or `localhost` (with any port); others get 400. A state-changing request (`POST`) with an `Origin` header must come from `http://127.0.0.1:<port>` or `http://localhost:<port>`; others get 403. This blocks DNS-rebinding and cross-site requests from pages in the owner's browser.
5. **Paid consent.** A metered row with `allow_paid_api` false is rejected with 400 before anything starts: `Metered <provider> API: <model_id>.` followed by the paid gate's text (`Paid API requires --allow-paid-api when non-interactive`). A subscription row with `allow_paid_api` true is rejected with 400 and the CLI's text (`--allow-paid-api requires a metered --provider`). The child gets `--allow-paid-api` only when both agree, and its stdin is `/dev/null`, so the paid gate can never show the interactive `USE_API` prompt.
6. **Stop.** `POST /runs/current/stop` sends `SIGINT` to the child's process group, the same signal as Ctrl-C in a terminal. Saved batches stay in the checkpoint and resume on the next run; the batch in flight is lost, and on a metered row it may already be paid for. The endpoint description says so.

Also in this phase, from §2 and §3:

- **One run at a time.** `POST /runs` returns 409 while the run record names a live process.
- **Request body:** `source`, `output`, `row` (an Enum of the enabled rows), optional `prompt` and `glossary` (passed as `--prompt=<text>`, one token so a leading dash is safe, and `--glossary`), and `allow_paid_api` (default false). Other CLI options stay CLI-only.
- **Status:** `state` is `running`, `finished` (exit code 0), `failed` (non-zero), `stopped` (exit by `SIGINT`), or `ended` (exit not observed), plus `planned_segments`, `done_segments`, `checkpoint_dir`, `log_path`, and the last 20 log lines.
- **Child command:** the same interpreter runs `-m ai.cli <source> --output <output> --row <row> [...]`, the CLI contract `bookweaver` uses.

Phase 4's rejection rule is implemented here by decision 5; Phase 4 keeps only its offline tests that no metered row starts without consent.

### 7.4 Phase 4 as built (2026-11-08)

Phase 4 adds tests only; no product code changed. `tests/unit/test_local_api.py` takes the rows from `enabled_rows()`, so a new metered row is covered without a test change. No test makes a paid call.

- Every metered row without consent (field omitted or false) returns 400 with its provider and model. A null value returns 422. In each case no record, log or child exists.
- Every metered row with consent gives the child `--allow-paid-api` exactly once. Consent is not remembered for the next run.
- Every subscription row refuses consent and never gets the flag.
- The child's stdin is `/dev/null`, even when the server's own stdin is something else.
- Second layer: the real CLI, started with `/dev/null` stdin and no provider keys, refuses every metered row without the flag and writes no output.

Each of these fails when its check is removed (checked by temporarily editing the server gate, the flag rule, the stdin setting and the factory gate).

## 8. Verification

- Offline tests at the HTTP boundary with a fake `bookweaver` child process: argument derivation per row, rejection of rows not in the registry, paid-row consent, status read from a fixture checkpoint.
- The server binds to `127.0.0.1` only; a test asserts this.
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`, `uv run tach check`.
