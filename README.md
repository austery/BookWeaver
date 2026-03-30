BookWeaver
==========

BookWeaver is a document translation pipeline for long books (`.epub`, `.pdf`, `.docx`) using Gemini CLI or Gemini API, with EPUB-first output and bilingual merge support.

## What it does

- Converts input files to markdown chunks
- Translates chunks with Gemini models
- Merges source + translation into bilingual markdown
- Renders HTML and exports final formats (EPUB/DOCX/PDF or HTML-only)

## Quick start

### Workflow selection (important)

| Input type | Goal | Recommended workflow | Command |
|---|---|---|---|
| EPUB | Preserve package structure/navigation fidelity | `epub` | `./translatebook.sh --workflow epub /path/to/book.epub` |
| PDF/DOCX | Convert then translate | `markdown` | `./translatebook.sh --workflow markdown /path/to/book.pdf` |
| EPUB (legacy command) | Backward compatibility only | `epub` | `./translatebook.sh --epub-translate-roundtrip /path/to/book.epub` |

Default behavior:

- EPUB input defaults to `--workflow epub`
- non-EPUB input defaults to `--workflow markdown`

### 1) Prerequisites

Choose one translation provider:

**Option A: Gemini CLI (recommended, default)**
- `gemini` CLI (authenticated)
- `ebook-convert` (Calibre)
- `pandoc`

```bash
which gemini
which ebook-convert
which pandoc
```

**Option B: Gemini API (alternative, experimental)**
- Google AI API key (set via env var, config file, or CLI parameter)
- `ebook-convert` (Calibre)
- `pandoc`

```bash
# Option B1: Use environment variable
export GEMINI_API_KEY="your-api-key-here"

# Option B2: Use config file (recommended for persistent setup)
# Edit config/config.json:
# {
#   "gemini_api": {
#     "enabled": true,
#     "api_key": "your-api-key-here",
#     "model": "gemini-2.5-flash"
#   }
# }

which ebook-convert
which pandoc
```

### 2) Dry-run first

```bash
./translatebook.sh --dry-run /path/to/book.epub
```

### 3) Real run

```bash
# EPUB package-preserving workflow (default for .epub input)
./translatebook.sh --workflow epub --output-format epub /path/to/book.epub

# EPUB workflow with automatic glossary extraction + injection
./translatebook.sh --workflow epub --extract-glossary --output-format epub /path/to/book.epub

# EPUB workflow with pre-extracted glossary and priority filtering
./translatebook.sh --workflow epub --glossary glossary.json --glossary-min-priority high --output-format epub /path/to/book.epub

# Force model for EPUB workflow
./translatebook.sh --workflow epub --model flash --output-format epub /path/to/book.epub
./translatebook.sh --workflow epub --model gemini-3-pro-preview --output-format epub /path/to/book.epub

# Markdown workflow (default for non-EPUB)
./translatebook.sh --workflow markdown --output-format epub /path/to/book.pdf

# HTML only output
./translatebook.sh --workflow markdown --output-format html /path/to/book.docx

# EPUB baseline roundtrip (no translation, zero text mutation)
./translatebook.sh --epub-baseline /path/to/book.epub

# Deprecated alias for EPUB workflow (still supported)
./translatebook.sh --epub-translate-roundtrip --olang zh /path/to/book.epub
```

Baseline mode writes output to `<input_basename>_temp/baseline_roundtrip.epub`.
EPUB workflow writes output to `<input_basename>_temp/translated_roundtrip.epub`.

### 3.1) Workflow behavior notes

**Markdown workflow (`--workflow markdown`):**

- Step 3 calls `ai.cli` directly:
  `python3 -u -m ai.cli <temp_dir> --input-format markdown --output <temp_dir>/output.md ...`
- `ai.cli` writes final bilingual `output.md` directly.
- Step 4 remains in the legacy step numbering but is now a no-op (informational skip).

**EPUB workflow (`--workflow epub`):**

- Translation is routed through `ai.cli`:
  `python3 -u -m ai.cli <book.epub> --input-format epub --output <temp_dir>/translated_roundtrip.epub ...`
- Legacy checkpoint resume is no longer used in this path.
- `--force-resume` is accepted for compatibility but ignored (the script prints a warning).

### 3.1a) Alternative: Use Gemini API instead of CLI (experimental)

If you encounter persistent `AbortError` or capacity issues with Gemini CLI, you can use the direct Gemini API as an alternative:

```bash
# Set your API key
export GEMINI_API_KEY="your-api-key-here"

# Use API provider instead of CLI
./translatebook.sh --workflow epub --provider api --output-format epub /path/to/book.epub

# Keep CLI as primary but allow fallback to API on CLI failures
./translatebook.sh --workflow epub --provider cli --fallback-provider api --output-format epub /path/to/book.epub
```

**Advantages of API provider:**
- More stable and predictable error handling
- Better rate limit recovery with explicit retry delays
- Programmatic control over timeouts and retries
- Clear distinction between temporary (429) and permanent quota errors

**Current status:**
- Gemini API provider is now available via `--provider api`
- CLI provider remains the default (`--provider cli`)
- API provider requires `GEMINI_API_KEY` or `gemini_api.api_key` in config
- Optional fallback is available via `--fallback-provider api` (only when `--provider cli`)

Common commands:

```bash
# Continue from translation to render/export
./translatebook.sh --start-step 3 --output-format epub /path/to/book.epub

# Continue from Step 4 bridge (no-op) to render/export if output.md already exists
./translatebook.sh --start-step 4 --output-format epub /path/to/book.epub

# Re-run translation step with explicit model/prompt overrides
./translatebook.sh --start-step 3 --output-format epub /path/to/book.epub
```

### 3.2) EPUB preflight check (optional, recommended)

Before expensive translation runs, check EPUB quality first:

```bash
# If epubcheck is installed
epubcheck /path/to/book.epub
```

If preflight reports structural/link issues (for example broken `href#fragment`),
clean the book manually in tools like Sigil/Calibre first, then run BookWeaver.

Note: EPUB workflow now tolerates pre-existing source broken fragments
(it only blocks newly introduced broken links), but source-quality cleanup is still
recommended for better reader compatibility.

### 4) Sample workflow (first 3 chunks)

```bash
python3 01_convert_to_htmlz.py /path/to/book.epub
# prepare a sample temp dir with page0001~page0003.md
python3 -u -m ai.cli <sample_temp_dir> --input-format markdown --output <sample_temp_dir>/output.md --model gemini-2.5-flash --output-lang zh
```

## Pipeline

1. `01_convert_to_htmlz.py` (normalize and split)
2. `ai.cli` translation step (invoked by `translatebook.sh` step 3)
3. Step 4 bridge (no-op; merged `output.md` already produced by `ai.cli`)
4. `05_md_to_html.py` (HTML rendering)
5. `06_add_toc.py` (TOC)
6. `07_generate_formats.py` (EPUB/DOCX/PDF generation)

## Quality gate (lint and test)

Run the same checks locally before pushing:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

CI uses workflow `lint-and-test` with a strict order:

1. lint (`ruff check` + `ruff format --check`)
2. test (`pytest`) after lint passes

If lint or tests fail, the CI gate is blocking and the change is not merge-ready.
See `docs/architecture/specs/SPEC-003-lint-quality-gates.md` for the formal policy.

## Troubleshooting

### Gemini CLI AbortError or capacity issues

If you encounter persistent `AbortError: The user aborted a request` or similar capacity errors:

**Immediate solutions:**
1. **Wait and retry** - Gemini CLI has traffic prioritization limits that vary by time of day
2. **Switch model and retry** - current `ai.cli` workflow does not support checkpoint resume:
   ```bash
    # Initial run with flash
    ./translatebook.sh --workflow epub --model flash book.epub
    
    # If flash fails, retry with pro
    ./translatebook.sh --workflow epub --model pro book.epub
    ```
3. **Use Gemini API (experimental)** - More stable alternative to CLI:
   ```bash
   export GEMINI_API_KEY="your-api-key"
   ./translatebook.sh --workflow epub --provider api book.epub
   ```
4. **Use CLI + API fallback (opt-in)** - Keep CLI first, auto-fallback to API:
   ```bash
   export GEMINI_API_KEY="your-api-key"
   ./translatebook.sh --workflow epub --provider cli --fallback-provider api book.epub
   ```

**Root cause:**
Gemini CLI 0.35.0+ has strict traffic prioritization and internal loop recovery logic that aborts requests if they exceed internal timeout thresholds. This is a known limitation documented in [Gemini CLI updates](https://goo.gle/geminicli-updates).

**Workarounds:**
- Avoid peak traffic hours (9 AM - 6 PM Pacific time usually has higher limits)
- Try early morning or late night runs
- Use `--model pro` if you have higher tier access
- Consider using Gemini API provider for production workloads

### EPUB resilience tuning (advanced, optional)

You can tune retry/split/circuit-breaker behavior in `config/config.json`:

```json
{
  "epub_resilience": {
    "rate_limit_backoff_seconds": [60, 120],
    "timeout_backoff_seconds": [60],
    "transient_backoff_seconds": [45],
    "max_split_depth": null,
    "doc_failure_budget": null,
    "failed_docs_path": null,
    "cli_api_fallback_enabled": false,
    "pro_timeout_seconds": 300,
    "non_pro_timeout_seconds": 180
  }
}
```

Notes:
- Defaults preserve current behavior.
- `doc_failure_budget` enables a document-level circuit breaker.
- `failed_docs_path` writes failed-document diagnostics as JSON.
- CLI argument `--cli-api-fallback` (used internally by `--fallback-provider api`) can force fallback on for a run.

## Prompt definition

Prompt rendering is profile-driven:

- `config/prompts/default_prompt.txt`
- `config/prompts/ebook_prompt.txt`
- selected via `config/config.json.example` (`prompt_profile`, `prompt_templates`)
- `{GLOSSARY_BLOCK}` placeholder injected with terminology constraints (see glossary section below)

You can append extra instructions with:

```bash
./translatebook.sh -p "Your custom translation constraints" /path/to/book.epub
```

## Glossary extraction & injection (SPEC-010)

BookWeaver can automatically extract terminology from EPUB index/TOC and inject it as translation constraints via prompt injection.

### Quick start

**Automatic extraction + injection (single command):**
```bash
./translatebook.sh --workflow epub --extract-glossary --output-format epub /path/to/book.epub
```

**Manual extraction (pre-run glossary preparation):**
```bash
# Extract glossary JSON from EPUB
uv run python3 00_extract_glossary.py /path/to/book.epub --output glossary.json --model pro

# View extracted terms
cat glossary.json | jq '.[0:3]'  # First 3 terms

# Translate with glossary
./translatebook.sh --workflow epub --glossary glossary.json --output-format epub /path/to/book.epub
```

### Priority-based filtering

By default, glossary injection includes all terms. Use `--glossary-min-priority` to reduce prompt bloat:

```bash
# Only inject critical + high priority terms (excludes medium, reduces prompt by ~60%)
./translatebook.sh --workflow epub --glossary glossary.json --glossary-min-priority high --output-format epub /path/to/book.epub

# Only inject critical terms (most aggressive filtering, ~85% reduction)
./translatebook.sh --workflow epub --glossary glossary.json --glossary-min-priority critical --output-format epub /path/to/book.epub
```

**Priority levels** (extracted by AI analysis):
- `critical` — Core domain concepts essential for accurate translation
- `high` — Important terms that appear frequently
- `medium` — Supporting vocabulary with lower frequency (default inclusion, can be filtered)

### Extraction behavior

- **Index detection**: Two-pass approach (filename hints first, then content heuristics for Kindle-format EPUBs)
- **Default model**: Pro model (slower but more reliable terminology selection)
- **Full-index mode**: Use `--full-index` to extract all index entries without AI filtering (comprehensive but slower)
- **CLI→API fallback**: If Gemini CLI unavailable, automatically falls back to Gemini API (requires `GEMINI_API_KEY` or config)
- **API-only extraction**: Use `--api-key` to force direct API extraction:
  ```bash
  export GEMINI_API_KEY="your-api-key"
  uv run python3 00_extract_glossary.py /path/to/book.epub --output glossary.json --api-key $GEMINI_API_KEY
  ```

### Chapter-level A/B testing

To test glossary on specific chapters:
```bash
# Extract glossary
uv run python3 00_extract_glossary.py book.epub -o glossary.json

# Translate only Chapter 3-4 with glossary (--only-docs accepts EPUB spine doc indices)
./translatebook.sh --workflow epub --glossary glossary.json --only-docs 3,4 --output-format epub book.epub
```



## Important behavior notes

- `--epub-baseline` runs a dedicated roundtrip path and exits early from translation/rendering steps.
- Baseline output is `<temp_dir>/baseline_roundtrip.epub` and preserves source package content (no text mutation).
- Baseline parser extracts OPF path, cover metadata pointer, and spine order for structural validation.
- `--workflow epub` runs the EPUB package-preserving translation workflow and exits early from the legacy markdown pipeline.
- `--epub-translate-roundtrip` is a deprecated alias for `--workflow epub`.
- EPUB workflow output is `<temp_dir>/translated_roundtrip.epub`.
- EPUB workflow currently supports only `alternating` bilingual output and enforces strict integrity checks (fail-fast on errors).
- EPUB workflow uses per-document batch translation (`%%` segment separator) to reduce API call count versus per-segment calls.
- If batch output segment count mismatches, it automatically falls back to binary split retry for that document.
- In EPUB workflow, table cells are source-only (no `th/td` bilingual injection) for layout stability.
- Model fallback chain is intentionally out of scope for this phase.
- In markdown workflow, Step 3 (`ai.cli`) writes final bilingual `output.md` directly.
- Step 4 in markdown workflow is a no-op bridge for legacy step numbering.
- Step 5 renders markdown image syntax (`![](...)`) into `<img>` and keeps source-side `#` headings as real document headings.
- `--bilingual-style` currently supports only `alternating`.
- Step 6 can build TOC from markdown-style heading lines in HTML paragraphs, auto-creates a TOC container when missing, and defaults TOC entries to chapter-level (`h1`) headings.
- Step 7 resolves HTML input in order: `book_doc.html` -> `book.html` -> newest `*.html` in temp dir.
- Step 7 format conversion uses Calibre `ebook-convert` directly (no external publish script required).
- Model selection in Step 3 uses: requested model (or alias) -> `fallback_chain` -> probe availability.
- Gemini provider no longer uses a hardcoded static allow-list.

## EPUB baseline acceptance checklist

- Cover metadata pointer (`meta name="cover"`) remains resolvable after roundtrip.
- TOC/nav links stay clickable (no broken fragment links in validated docs).
- Manifest asset paths remain present (no missing image/css/font files).
- OPF spine order remains unchanged.

See `docs/architecture/specs/SPEC-005-epub-roundtrip-baseline.md` for baseline policy and limits.

## EPUB workflow acceptance checklist

- Generated EPUB exists at `<temp_dir>/translated_roundtrip.epub`.
- Spine XHTML content contains both source and translated text in alternating order.
- TOC/nav resource files remain unmodified in package-aware translation mode.
- Cover/toc/spine pointers remain resolvable.
- Fragment links and manifest asset references pass strict validation.

See `docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md` for EPUB workflow scope and limits.

### Translation strategy reference

This mode is kept as a separate feature path and currently translates spine XHTML with per-document batching (`%%` separators), while preserving segment alignment.

Design reference for future prompt/segmentation optimization:

- Immersive Translate `1.26.6` (paragraph-structure-preserving prompt style).

## Config

- Runtime config template: `config/config.json.example`
- Model aliases: `model_aliases` (`pro|flash|lite`)
- Probe cache config: `model_probe.cache_path` / `model_probe.cache_ttl_seconds`
- Ordered fallback: `fallback_chain`
- Quota DB: `~/.config/translatebook/quota.db`

### Gemini API Configuration (Optional)

For using Gemini API provider instead of CLI, configure in `config/config.json`:

```json
{
  "gemini_api": {
    "enabled": true,
    "api_key": "your-google-ai-api-key-here",
    "model": "gemini-2.5-flash"
  }
}
```

**API Key Priority** (highest to lowest):
1. `api_key` parameter (if passed to GeminiAPIProvider constructor)
2. `GEMINI_API_KEY` environment variable
3. `config['gemini_api']['api_key']` in config.json

**Recommended approach:**
- **Development**: Use `GEMINI_API_KEY` env var for quick testing
- **Production**: Use config file to persist settings
- **CI/CD**: Use env var to keep secrets out of version control

## Acknowledgements

This project was forked and reworked from:
https://github.com/wizlijun/claude_translater

Thanks to the original author and contributors for the foundation.

## License

MIT (see `LICENSE`)
