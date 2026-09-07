# BookWeaver

BookWeaver translates EPUB publications into alternating bilingual EPUBs. The canonical entry point is `uv run bookweaver`. The subscription runtime is Antigravity CLI (`agy`); Gemini API is a separately authorized paid path.

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

The public profiles are `flash` and `pro`. Flash supports low, medium, and high effort; Pro supports low and high. Omitted CLI effort means low. Medium/high selections still require live acceptance evidence; the current live probes cover Flash 3.8 Low and Pro 3.1 Low. Additional instructions can be supplied with `-p`; an existing terminology file can be supplied with `--glossary PATH`.

## Checkpoints

Each successfully validated batch saves accumulated translations and provenance to one atomically replaced `checkpoint.json`. One run owns its checkpoint lock at a time. A failed batch leaves earlier saved work reusable. Resume is enabled by default:

```bash
uv run bookweaver book.epub --output translated.epub
```

Running that command again restores matching segments. A fully restored book is repackaged without further translation calls. Save progress includes checkpoint bytes and elapsed time. Input or segmenter mismatches cannot be forced; language, effort, profile, prompt, or batching changes require explicit `--force-resume`. Concrete model changes produce a continuity warning. Known schema-v1 checkpoints can be imported without rewriting their original files; incompatible or incomplete state stops clearly.

## Paid API

CLI failure never automatically switches to API. Paid execution requires `--provider api` and either interactive `USE_API` confirmation or an explicit per-invocation capability:

```bash
uv run bookweaver book.epub --output translated.epub --provider api --allow-paid-api
```

This command may incur charges. It requires `GEMINI_API_KEY` or `gemini_api.api_key`. Config files cannot authorize spending. Explicit effort is not supported on the API path. Paid requests have one SDK attempt and no engine split retries. No live paid API test has been performed for this migration.

## Configuration migration

Runtime configuration is read from `config/config.json` and `~/.config/bookweaver/config.json`. The example file is a template, not a runtime default. Configuration is validated against `config/schemas/config_schema.json` before provider construction.

Old model aliases, model probes, fallback settings, output-format settings, and unused legacy controls fail with migration errors. An existing `~/.config/translatebook/config.json` also requires explicit migration. Back up user configuration before changing it. The reference example lists supported settings; model versions belong in the typed registry.

Custom prompt templates are optional. Supply a matching `prompt_profile` and `prompt_templates` mapping; templates may use `{TARGET_LANGUAGE}`, `{GLOSSARY_BLOCK}`, and `{CUSTOM_INSTRUCTIONS_BLOCK}`. Omitting them uses the built-in EPUB prompt.

## Scope and verification status

EPUB-to-EPUB is the supported product path. Table cells remain source-only for layout stability. Markdown/PDF adapters are retained behind `--allow-isolated-format`; EPUB glossary/resume controls do not apply there. DOCX is rejected. Legacy shell and numbered scripts are pending retirement and are not the supported entry point.

The migration is in progress. A small synthetic EPUB has completed through the new application composition with real Flash 3.8 Low and a full checkpoint restore. This is not whole-book acceptance. Large-batch fidelity, selected-book quality/layout checks, interruption recovery, and legacy deletion gates remain tracked in [SPEC-021](docs/architecture/specs/SPEC-021-runtime-convergence-and-book-validation.md).

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run tach check
```
