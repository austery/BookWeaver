# CLAUDE.md (BookWeaver contributor notes)

This is a concise contributor guide. User-facing usage is in `README.md`.

## Scope

- Runtime backend: Gemini CLI
- Preferred final output: EPUB
- Bilingual style support in current code: `alternating` only

## Key entrypoints

- `translatebook.sh` — main orchestrator
- `00_extract_glossary.py` — optional pre-step: extract terminology glossary from EPUB index/toc
- `01_convert_to_htmlz.py` — convert input to markdown chunks
- `03_translate_md.py` — translate chunks with model selection
- `04_merge_md.py` — merge source + translation
- `05_md_to_html.py` — render bilingual alternating HTML
- `07_generate_formats.py` — export requested final formats
- `08_epub_roundtrip_baseline.py` — EPUB baseline roundtrip (zero text mutation)
- `09_epub_translate_roundtrip.py` — EPUB package-aware translation roundtrip

## Prompt source

Translation prompt is loaded by profile from:

- `config/prompts/default_prompt.txt`
- `config/prompts/ebook_prompt.txt`
- selected via `config/config.json.example` (`prompt_profile`, `prompt_templates`)

Extra user constraints are appended by `-p/--prompt`.

## Current behavior to remember

- Step 3 output is translation-only (`output_pageXXXX.md`)
- Bilingual merged content is produced at Step 4 (`output.md`)
- `--epub-baseline` triggers a dedicated baseline path and exits after generating `baseline_roundtrip.epub`
- `--workflow epub` triggers package-preserving EPUB translation and exits after generating `translated_roundtrip.epub`
- `--epub-translate-roundtrip` is a deprecated alias for `--workflow epub`
- default workflow resolution: EPUB input -> `epub`, non-EPUB input -> `markdown`
- `--output-format` is handled in Step 7 (`html` skips conversion)
- `--extract-glossary` triggers `00_extract_glossary.py` before EPUB translation; writes `{temp_dir}/extracted_glossary.json`
- `--glossary <path>` passes a pre-extracted glossary directly to the EPUB translation step
- `--glossary-min-priority` (default: all) filters glossary terms: `critical`, `high`, or `all` (excludes lower priorities to reduce prompt bloat)
- `--only-docs <indices>` limits EPUB translation to specific spine docs (comma-separated, useful for A/B testing); e.g., `--only-docs 3,4`
- Glossary block injected via `{GLOSSARY_BLOCK}` placeholder in prompt templates (before `{CUSTOM_INSTRUCTIONS_BLOCK}`); empty string when no glossary
- Glossary extraction uses Pro model by default (reliable terminology selection), supports `--full-index` for comprehensive extraction without AI filtering
- `--model` accepts aliases (`pro|flash|lite`) and full model names
- Step 3 model selection:
  1. Chunk size (if thresholds configured) → ModelSelector
  2. CLI --model parameter override
  3. Alias resolution (pro → gemini-2.5-pro)
  4. Probe availability check (test if model accessible)
  5. Fallback chain (try alternatives if requested unavailable)
- CI quality gate uses workflow `lint-and-test` with blocking lint -> test sequencing (see `docs/architecture/specs/SPEC-003-lint-quality-gates.md`)
- Baseline quality contract and limits are defined in `docs/architecture/specs/SPEC-005-epub-roundtrip-baseline.md`
- Translate roundtrip quality contract and limits are defined in `docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md`
- EPUB workflow keeps table cells source-only for layout stability (no `th/td` bilingual injection)
- Pro model in EPUB workflow pre-batches large chapter requests with a char-only limit (60K chars per batch) before recursive split-retry
- SPEC-010 provides terminology extraction & glossary injection (Strategy A MVP) with priority-based filtering
- SPEC-011 provides ModelResolver + ProviderFactory for model routing and API fallback

## SPEC-010 & SPEC-011 Architecture

### SPEC-010: Terminology Extraction & Glossary Injection

**Strategy A MVP (implemented)**:

1. **Extraction Stage** (offline, single-run):
   - `00_extract_glossary.py` uses Pro model to analyze EPUB index/TOC
   - Two-pass EPUB index detection: filename hints (fast) → content heuristics (Kindle fallback)
   - Outputs JSON glossary with priority labels (`critical`, `high`, `medium`)
   - CLI→API fallback: uses Gemini API if CLI unavailable (config-based api_key resolution)
   - Timeout: 600 seconds for large prompts

2. **Injection Stage** (runtime, per-chunk):
   - `GlossaryInjector.format_block(min_priority=)` loads glossary and filters by priority
   - Injects via `{GLOSSARY_BLOCK}` placeholder in prompt (before `{CUSTOM_INSTRUCTIONS_BLOCK}`)
   - Priority filtering reduces prompt bloat by 60-85% without losing core constraints

**Key Files**:
- `ai/glossary_injector.py` — Priority-based filtering and formatting
- `ai/glossary_extractor.py` — Two-pass index detection (Kindle-aware)
- `00_extract_glossary.py` — CLI entry with CLI→API fallback
- `config/schemas/glossary_schema.json` — JSON validation schema
- `ai/epub_translate_roundtrip.py` — Glossary threading through EPUB translation

### SPEC-011: Model Routing & Provider Factory

**Implemented**:

1. **ModelResolver**: Centralizes model alias resolution + availability probing
   - Alias resolution: `pro|flash|lite` → full model name
   - Availability probing: Tests model accessibility before use
   - Fallback chain support

2. **ProviderFactory**: Abstracts provider selection (CLI vs API)
   - CLI provider (default)
   - API provider (Gemini API, requires api_key)
   - Fallback-capable: CLI → API on failures

**Key Files**:
- `ai/model_resolver.py` — Model alias + probe logic
- `ai/provider_factory.py` — Provider selection and instantiation
- `ai/gemini_api_provider.py` — Google Gemini API client (uses new `genai.Client` SDK)

## Dev verification

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
bash -n translatebook.sh
uv run python -m py_compile 03_translate_md.py ai/gemini_provider.py ai/model_probe.py 05_md_to_html.py 07_generate_formats.py ai/glossary_injector.py ai/glossary_extractor.py
```

## Acknowledgements

BookWeaver is reworked from:
https://github.com/wizlijun/claude_translater
