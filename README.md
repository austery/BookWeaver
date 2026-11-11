# BookWeaver

BookWeaver translates an EPUB into an alternating bilingual EPUB: each source paragraph is followed by its translation. It runs on your own subscription CLIs: Antigravity (`agy`, the default), Codex, or Claude Code. A paid API (Gemini, Anthropic) runs only with your consent for each run. EPUB is the only input format ([ADR-0003](docs/architecture/decisions/0003-epub-only-product.md)).

## Install

Install Python 3.13+, [uv](https://docs.astral.sh/uv/), and an authenticated Antigravity CLI. Then:

```bash
uv sync --frozen
```

## Translate a book

```bash
uv run bookweaver book.epub --output translated.epub
```

- The run translates in batches and saves progress after each batch.
- Add `--extract-glossary` to extract the book's key terms first, so the whole book translates them the same way (see [Terms](docs/guides/terms.md)). The browser upload does this by default.
- Run the same command again to resume after a failure or Ctrl-C. Finished batches are not translated again.
- To choose another model, list the presets and pass one:

```bash
uv run bookweaver presets
```

```bash
uv run bookweaver book.epub --output translated.epub --preset agy-pro-low
```

A paid preset (`gemini-*`, `anthropic-*`) costs money. It runs only with `--allow-paid-api` or when you type `USE_API` at the prompt, and that consent covers one run. A configuration file cannot give it.

## Translate from a browser

```bash
uv run bookweaver serve
```

Open <http://127.0.0.1:8765/docs>, use `POST /runs/upload` to upload the EPUB and choose a preset, and read the progress with `GET /runs/current`. Uploaded books and their translations are kept in `~/Documents/BookWeaver/<book name>/`.

Keep books, translations and checkpoints outside this program folder. A checkpoint is saved in `.bookweaver_checkpoints/` beside the output file.

## Guides

| Guide | Read it to |
|---|---|
| [Presets and models](docs/guides/presets-and-models.md) | choose a model, set up Codex or Claude Code, compare models, run a paid API |
| [Local API](docs/guides/local-api.md) | use the browser page and the other endpoints |
| [Terms](docs/guides/terms.md) | understand term extraction, supply your own glossary, run a Term Panel |
| [Checkpoints, batches and configuration](docs/guides/checkpoints-and-configuration.md) | resume rules, batch size, timeouts, configuration files, older checkpoints |

## Project status and contributing

Contributor rules, verification commands and the current product boundary are in [AGENTS.md](AGENTS.md). Validation status and remaining acceptance work are in [SPEC-021](docs/architecture/specs/SPEC-021-runtime-convergence-and-book-validation.md). Architectural decisions are recorded in [ADRs](docs/architecture/decisions/). Domain terms are defined in [GLOSSARY.md](GLOSSARY.md).
