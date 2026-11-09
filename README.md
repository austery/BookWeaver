# BookWeaver

BookWeaver translates EPUB publications into alternating bilingual EPUBs. The canonical entry point is `uv run bookweaver`. The default subscription runtime is Antigravity CLI (`agy`); Codex CLI is an experimental second one, selected by preset. The Gemini, Anthropic, and OpenAI APIs are separately authorized paid paths.

## Setup and translation

Install Python 3.13+, uv, and an authenticated Antigravity CLI, then synchronize the locked environment:

```bash
uv sync --frozen
uv run bookweaver book.epub --output translated.epub
```

The default is Flash 3.8 Low. Model mappings live in `ai/model_profiles.py`; upgrading a model requires changing that registry and verifying the new version. A missing model stops execution rather than silently switching versions.

```bash
uv run bookweaver book.epub --output translated.epub --model pro --effort low
uv run bookweaver book.epub --output translated.epub --extract-glossary
```

The public profiles are `flash` and `pro`. Flash supports low, medium, and high effort; Pro supports low and high. Omitted CLI effort means low. Medium/high selections still require live acceptance evidence; the current live probes cover Flash 3.8 Low and Pro (`gemini-4-argon`) Low. A pair of `agy` version and model with no recorded evidence runs a short automatic check before its first book batch. A model that `agy models` does not list stops the run before that check. Additional instructions can be supplied with `-p`; an existing terminology file can be supplied with `--glossary PATH`.

## Named presets

A preset is a short name for one provider, model profile, and effort. List the enabled presets, with their status and evidence:

```bash
uv run bookweaver presets
```

Use `--preset` in place of `--model`, `--effort`, and `--provider`. You cannot combine them.

```bash
uv run bookweaver book.epub --output translated.epub --preset agy-pro-low
```

Presets that start with `agy-` use the Antigravity subscription, and `codex-` presets use the ChatGPT subscription. The `gemini-` and `anthropic-` presets are paid. A preset name does not give consent. Each paid run still needs the [paid API](#paid-api) consent.

Codex presets use their own login, so your Codex rules and skills do not reach a translation. Set it up once:

```bash
mkdir -p ~/.local/state/bookweaver/codex-home
```

```bash
CODEX_HOME=~/.local/state/bookweaver/codex-home codex login
```

## Local API

Start the local API server. It stays in the foreground of your terminal, on `127.0.0.1` only:

```bash
uv run bookweaver serve
```

Then open <http://127.0.0.1:8765/docs> in a browser. That page is the user interface. It loads its assets from a CDN. Without network the page is blank, but the endpoints still work. Use `--port` to choose another port. Press Ctrl-C to stop the server.

`uv sync --frozen` already installs what the server needs. To run without the dev tools, start the server with `uv run --no-dev --extra api bookweaver serve`. An installed package also needs the `api` extra.

### Translate a book

1. Open `POST /runs/upload` on the `/docs` page and press **Try it out**.
2. Choose the EPUB in `file` (at most 200 MiB).
3. Confirm the output name. Leave `output_name` empty to use `<book name>.zh.epub`.
4. Choose the `preset` from the list. The default is `agy-flash-low`. Choose the `extraction_model`, the model that extracts the book's key terms. The default is `pro`.
5. Press **Execute**. The translation starts at once and uses quota or money, as the preset says.
6. Use `GET /runs/current` to read the progress: compare `done_segments` with `planned_segments`. It also shows the state and the last log lines. Press **Execute** again to refresh.

A failed run shows its reason in the last log lines. If the Antigravity quota is used up, the line names the model and the time until the quota resets.

The book and its translation stay in one folder. `<book name>` is the uploaded file name without `.epub`, not the title inside the book.

```text
~/Documents/BookWeaver/<book name>/
  <book name>.epub       the uploaded copy
  <book name>.zh.epub    the translation
```

The run log and the saved progress are in the same folder.

- Upload the same file with the same preset and prompt to resume. A different prompt, profile, or effort fails, because the API has no `--force-resume`; use the CLI for that.
- Each Codex preset works in its own `<preset>/` folder inside the book's folder, so you can upload the same book again with another Codex model and compare the results.
- A preset from another vendor with the same profile and no effort setting (for example `gemini-flash` to `anthropic-flash`) resumes with a warning. The book then mixes translations from two models.
- BookWeaver never replaces the uploaded copy. A different file with the same name returns 409. Rename the file to upload it.
- A new run rewrites the translation file. Copy the file first if you edited it by hand.
- A paid preset needs `allow_paid_api` set to `true`. Without it, the server returns 400 and stores nothing. The consent covers this run only.

### Other endpoints

| Endpoint | Action |
|---|---|
| `GET /presets` | List the enabled presets, the same as `bookweaver presets --json`. |
| `POST /runs/current/stop` | Stop the run, the same as Ctrl-C on the CLI. |

Scripts can start a translation from paths on this Mac with `POST /runs`. The `/docs` page does not show this endpoint. Only one translation can run at a time.

```bash
curl -X POST http://127.0.0.1:8765/runs \
  -H 'Content-Type: application/json' \
  -d '{"source": "/absolute/path/book.epub", "output": "/absolute/path/translated.epub", "preset": "agy-flash-low"}'
```

- Use absolute paths with `POST /runs`. The server resolves a relative path against the directory where you started it. The output directory must already exist.
- A paid preset needs `"allow_paid_api": true` in that request. Without it, the server returns 400 and starts nothing.
- The translation runs as a separate `bookweaver` process. It keeps running if you stop the server. A restarted server can still show and stop it, but cannot read its exit code.
- A stop keeps the saved batches for a later run. It loses the batch in progress. On a paid preset, the vendor may already have charged for that batch.
- The log of each run is in `.bookweaver_runs/<run_id>.log` beside the output file. The current run record is `$XDG_STATE_HOME/bookweaver/current-run.json` (default `~/.local/state/bookweaver/`).

### Term extraction

Before the first translation batch, a run extracts the book's key terms and uses them for the whole book. The upload uses the `pro` profile for this step by default, even when the preset is a `flash` one, so the step draws on Pro quota. The owner's earlier tests found Pro better at this step, so `flash` can lower the quality of the terms. The log names the model that the step uses.

The extraction prompt asks for one translation per term and puts other acceptable ones in a separate `alternatives` field. If a translation still contains a slash, the log names the term and the glossary stays as it is, because a slash can also belong to one translation. After an EPUB run with a glossary, `term-consistency.json` in the checkpoint directory shows how each term was translated. It is a signal, not a verdict: a plural source form is not matched, a sound rewording counts as missing, and a part of a compound translation can count as another option.

Automatic extraction reads the book's back-of-book index and table of contents. If the book has no usable index, the run stops before it calls a model, and the log names the choices. To continue, choose one of these:

- Set `glossary_mode` to `deep-scan` on the upload, or pass `--glossary-mode deep-scan` on the CLI. This sends the whole book in one request, which can use much more quota. It has no live evidence on any subscription CLI yet (issue #71).
- Supply terms with `--glossary PATH` on the CLI.

Choose the model with `extraction_model` on the upload or `--extraction-model` on the CLI. Without the CLI flag, `POST /runs` and the CLI use `terminology_extraction.extraction_model` from the configuration. Different terms change the prompt, so a saved run does not resume with another model's terms.

## Batch size and fidelity

Active EPUB runs default to at most 200 segments and 60,000 source characters per batch. The first reached limit closes a batch; an individually oversized segment remains alone for the existing split-retry policy. The segment cap avoids sending hundreds of short notes in one request. Smaller caps add request overhead but reduce work exposed to a failed batch; 200 is an initial operational setting, not a measured optimum.

```bash
uv run bookweaver book.epub --output translated.epub --max-batch-segments 150
```

The CLI overrides `epub_resilience.max_batch_segments` in configuration (positive integer). Character limits remain independently configurable. Legacy and isolated-format batchers have no segment cap unless explicitly supplied.

Each Antigravity batch waits up to 600 seconds for a response by default. Large batches or the Pro profile may need longer; set `antigravity.timeout_seconds` (positive number, at most 86400) in configuration. Codex has the same default and `codex.timeout_seconds`. A timed-out batch fails without automatic retry or paid fallback; committed batches remain resumable.

Dedicated bibliography pages remain source-only, including their headings. Detection uses bibliography semantics on the XHTML body, or a sole leading heading exactly matching Bibliography, References, Works Cited, or their supported Chinese equivalents. Filenames and prose mentions do not trigger exclusion. Mixed pages with additional headings stay translatable; bibliographies with subsection headings may require future section-level support. Table cells also remain source-only.

For focused review, add instructions with `-p` to preserve numerical ranges, negation scope, possibility versus certainty, and only explicitly stated causes. These are prompting and editorial-review practices, not an automatic semantic correctness guarantee. See the [selected-chapter review and revision ledger](docs/plans/2026-09-07-book-quality-polish.md).

## Checkpoints

Each successfully validated batch saves accumulated translations and provenance to one atomically replaced `checkpoint.json`. One run owns its checkpoint lock at a time. A failed batch leaves earlier saved work reusable. Resume is enabled by default:

```bash
uv run bookweaver book.epub --output translated.epub
```

Running that command again restores matching segments. A fully restored book is repackaged without further translation calls. Save progress includes checkpoint bytes and elapsed time. Input or segmenter mismatches cannot be forced; language, effort, profile, prompt, or batching changes require explicit `--force-resume`. Concrete model changes produce a continuity warning, except that a resume crossing a Codex model also requires `--force-resume`. Known schema-v1 checkpoints can be imported without rewriting their original files; incompatible or incomplete state stops clearly.

## Paid API

CLI failure never automatically switches to an API. Metered providers are selected by vendor and share one any-llm adapter ([SPEC-024](docs/architecture/specs/SPEC-024-metered-openai-anthropic-providers.md)):

| `--provider` | `flash` | `pro` | Key |
|---|---|---|---|
| `gemini` | `gemini-2.5-flash` | `gemini-2.5-pro` | `GEMINI_API_KEY` or `gemini_api.api_key` |
| `anthropic` | `claude-sonnet-5-5` | `claude-opus-5-5` | `ANTHROPIC_API_KEY` |
| `openai` | not yet pinned; fails before any request | | `OPENAI_API_KEY` |

Paid execution needs your consent for each run: type `USE_API` at the interactive prompt, or pass `--allow-paid-api`:

```bash
uv run bookweaver book.epub --output translated.epub --provider anthropic --allow-paid-api
```

These commands may incur charges. Config files cannot authorize spending. `--provider api` was renamed to `--provider gemini`; existing checkpoints that recorded `api` still resume. Explicit `--effort` is not supported on metered providers (Anthropic is pinned to low effort). Each batch is one streamed request with retries disabled and no engine split retries; reaching the model's output cap stops the run with a suggestion to lower `--max-batch-chars`. `api.timeout_seconds` sets the per-request deadline (default 600). No live paid API test has been performed for these providers.

## Configuration migration

In a source checkout, runtime configuration is read from checkout `config/config.json`, then `~/.config/bookweaver/config.json` (user values override checkout values). An installed wheel reads only `~/.config/bookweaver/config.json`; neither the working directory nor the installation directory supplies project configuration. The example file is a template, not a runtime default. Configuration is validated against `ai/config_schema.json` before provider construction.

Old model aliases, model probes, fallback settings, output-format settings, and unused legacy controls fail with migration errors. An existing `~/.config/translatebook/config.json` also requires explicit migration. Back up user configuration before changing it. The reference example lists supported settings; model versions belong in the typed registry.

Custom prompt templates are optional. Supply a matching `prompt_profile` and `prompt_templates` mapping; templates may use `{TARGET_LANGUAGE}`, `{GLOSSARY_BLOCK}`, and `{CUSTOM_INSTRUCTIONS_BLOCK}`. Omitting them uses the built-in EPUB prompt.

## Scope and verification status

EPUB-to-EPUB is the supported product path. Table cells remain source-only for layout stability. Markdown/PDF adapters are retained behind `--allow-isolated-format`; EPUB glossary/resume controls do not apply there. DOCX is rejected. Legacy shell and numbered scripts are pending retirement and are not the supported entry point.

The migration remains partially accepted. One complete narrative EPUB has run through Flash 3.8 Low with controlled interruption/resume and zero-call full restore. Its [initial validation](docs/plans/2026-09-07-stoic-joy-book-validation.md) and [three-chapter quality revision](docs/plans/2026-09-07-book-quality-polish.md) record evidence and limitations. A second book ran through the local API upload on 2026-11-08, and the owner read the result and accepted its layout and format. Complete reader/layout acceptance, additional books, full CLI/config coverage, and legacy retirement remain tracked in [SPEC-021](docs/architecture/specs/SPEC-021-runtime-convergence-and-book-validation.md). Codex runs through `--preset codex-*` (SPEC-025 §3.9); quality comparison has not run.

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run tach check
uv run python scripts/check_doc_links.py
```

### Checkpoint identity migration

New EPUB checkpoints and glossary cache keys use a streamed SHA-256 digest of the input file bytes. Identical bytes can resume through the same checkpoint directory after a move or timestamp change; changed bytes cannot resume, even with `--force-resume`. Checkpoint integrity and hard identity fields are checked before automatic glossary extraction.

The source-only bibliography policy uses segmenter `epub-leaf-block-v4-source-only-bibliography`. Older v3 checkpoints, including v1 imports, cannot resume into this policy even with force; preserve them and use a fresh `--checkpoint-dir`. A missing segment-cap field in an otherwise matching checkpoint means the historical unbounded policy; selecting a cap requires explicit force. Changing only the cap is a soft mismatch. The reviewed book is a separately documented reconstruction, not an automatic v3-to-v4 checkpoint migration.

Early schema-v2 checkpoints from PR #25's initial commit used metadata fingerprints. They cannot be reused as content-verified checkpoints: preserve the old directory and choose a fresh `--checkpoint-dir`. Legacy v1 imports require a matching legacy metadata fingerprint plus explicit `--force-resume`; imported segment provenance records `source_verification: legacy_metadata_only`. This acknowledges that historical source bytes cannot be verified from v1 metadata. The original v1 files remain intact.

Isolated Markdown input must be a directory containing translatable numbered `page*.md` files. Ordinary Markdown files and empty page directories fail before writing an output.
