# Local API

Run translations from a browser page on this Mac.

Start the local API server. It stays in the foreground of your terminal, on `127.0.0.1` only:

```bash
uv run bookweaver serve
```

Then open <http://127.0.0.1:8765/docs> in a browser. That page is the user interface. It loads its assets from a CDN. Without network the page is blank, but the endpoints still work. Use `--port` to choose another port. Press Ctrl-C to stop the server.

`uv sync --frozen` already installs what the server needs. To run without the dev tools, start the server with `uv run --no-dev --extra api bookweaver serve`. An installed package also needs the `api` extra.

## Translate a book

1. Open `POST /runs/upload` on the `/docs` page and press **Try it out**.
2. Choose the EPUB in `file` (at most 200 MiB).
3. Confirm the output name. Leave `output_name` empty to use `<book name>.zh.epub`.
4. Choose the `preset` from the list. The default is `agy-flash-low`. Choose the `extraction_model`, the model that extracts the book's key terms (see [Terms](terms.md)). The default is `pro`. To let several vendors choose the terms instead, choose a `term_panel` from your configuration; the default `none` keeps `extraction_model`. A panel ignores `extraction_model` and cannot be combined with `glossary_mode` `deep-scan`.
5. Press **Execute**. The translation starts at once and uses quota or money, as the preset says.
6. Use `GET /runs/current` to read the progress: compare `done_segments` with `planned_segments`. It also shows the state and the last log lines. Press **Execute** again to refresh.

A failed run shows its reason in the last log lines. If the Antigravity quota is used up, the line names the model and the time until the quota resets.

The book and its translation stay in one folder. `<book name>` is the uploaded file name without `.epub`, not the title inside the book.

```text
~/Documents/BookWeaver/<book name>/
  <book name>.epub       the uploaded copy
  <book name>.zh.epub    the translation
  <codex or claude preset>/  that run's translation, log, and saved progress
  panel-<name>-<id>/<preset>/  a Term Panel run's translation, log, and saved progress
  .bookweaver_glossaries/panel/  the Term Panel glossaries, shared by every preset
```

The run log and the saved progress are in the same folder as the translation.

- Upload the same file with the same preset and prompt to resume. A different prompt, profile, or effort fails, because the API has no `--force-resume`; use the CLI for that.
- Each Codex or Claude Code preset works in its own `<preset>/` folder inside the book's folder, so you can upload the same book again with another of those models and compare the results. Each folder extracts its own terms, so such a comparison can differ in its glossary as well as its model.
- With a Term Panel, every preset works in `panel-<name>-<id>/<preset>/` and all of them share the panel's glossary, which the first run creates; later uploads with another preset reuse it with no model call. `<id>` comes from the panel's members and the book, so after you edit a panel, the next upload starts in a new folder instead of resuming with other terms. The panel list is read when the server starts; restart it after you change `terminology_panels`.
- A preset from another vendor with the same profile and no effort setting (for example `gemini-flash` to `anthropic-flash`) resumes with a warning. The book then mixes translations from two models.
- BookWeaver never replaces the uploaded copy. A different file with the same name returns 409. Rename the file to upload it.
- A new run rewrites the translation file. Copy the file first if you edited it by hand.
- A paid preset needs `allow_paid_api` set to `true`. Without it, the server returns 400 and stores nothing. The consent covers this run only.

## Other endpoints

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

