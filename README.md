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

## Batch size and fidelity

Active EPUB runs default to at most 200 segments and 60,000 source characters per batch. The first reached limit closes a batch; an individually oversized segment remains alone for the existing split-retry policy. The segment cap avoids sending hundreds of short notes in one request. Smaller caps add request overhead but reduce work exposed to a failed batch; 200 is an initial operational setting, not a measured optimum.

```bash
uv run bookweaver book.epub --output translated.epub --max-batch-segments 150
```

The CLI overrides `epub_resilience.max_batch_segments` in configuration (positive integer). Character limits remain independently configurable. Legacy and isolated-format batchers have no segment cap unless explicitly supplied.

Dedicated bibliography pages remain source-only, including their headings. Detection uses bibliography semantics on the XHTML body, or a sole leading heading exactly matching Bibliography, References, Works Cited, or their supported Chinese equivalents. Filenames and prose mentions do not trigger exclusion. Mixed pages with additional headings stay translatable; bibliographies with subsection headings may require future section-level support. Table cells also remain source-only.

For focused review, add instructions with `-p` to preserve numerical ranges, negation scope, possibility versus certainty, and only explicitly stated causes. These are prompting and editorial-review practices, not an automatic semantic correctness guarantee. See the [selected-chapter review and revision ledger](docs/plans/2026-09-07-book-quality-polish.md).

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

The migration remains partially accepted. One complete narrative EPUB has run through Flash 3.8 Low with controlled interruption/resume and zero-call full restore. Its [initial validation](docs/plans/2026-09-07-stoic-joy-book-validation.md) and [three-chapter quality revision](docs/plans/2026-09-07-book-quality-polish.md) record evidence and limitations. Complete reader/layout acceptance, additional books, full CLI/config coverage, and legacy retirement remain tracked in [SPEC-021](docs/architecture/specs/SPEC-021-runtime-convergence-and-book-validation.md). Codex integration/comparison is deferred.

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run tach check
```

### Checkpoint identity migration

New EPUB checkpoints and glossary cache keys use a streamed SHA-256 digest of the input file bytes. Identical bytes can resume through the same checkpoint directory after a move or timestamp change; changed bytes cannot resume, even with `--force-resume`. Checkpoint integrity and hard identity fields are checked before automatic glossary extraction.

The source-only bibliography policy uses segmenter `epub-leaf-block-v4-source-only-bibliography`. Older v3 checkpoints, including v1 imports, cannot resume into this policy even with force; preserve them and use a fresh `--checkpoint-dir`. A missing segment-cap field in an otherwise matching checkpoint means the historical unbounded policy; selecting a cap requires explicit force. Changing only the cap is a soft mismatch. The reviewed book is a separately documented reconstruction, not an automatic v3-to-v4 checkpoint migration.

Early schema-v2 checkpoints from PR #25's initial commit used metadata fingerprints. They cannot be reused as content-verified checkpoints: preserve the old directory and choose a fresh `--checkpoint-dir`. Legacy v1 imports require a matching legacy metadata fingerprint plus explicit `--force-resume`; imported segment provenance records `source_verification: legacy_metadata_only`. This acknowledges that historical source bytes cannot be verified from v1 metadata. The original v1 files remain intact.

Isolated Markdown input must be a directory containing translatable numbered `page*.md` files. Ordinary Markdown files and empty page directories fail before writing an output.
