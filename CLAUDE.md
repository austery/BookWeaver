# CLAUDE.md (BookWeaver contributor notes)

This is a concise contributor guide. User-facing usage is in `README.md`.

## Scope

- Runtime backend: Gemini CLI
- Preferred final output: EPUB
- Bilingual style support in current code: `alternating` only

## Key entrypoints

- `translatebook.sh` — main orchestrator
- `01_convert_to_htmlz.py` — convert input to markdown chunks
- `03_translate_md.py` — translate chunks with model selection
- `04_merge_md.py` — merge source + translation
- `05_md_to_html.py` — render bilingual alternating HTML
- `07_generate_formats.py` — export requested final formats

## Prompt source

Translation prompt is loaded by profile from:

- `config/prompts/default_prompt.txt`
- `config/prompts/ebook_prompt.txt`
- selected via `config/config.json.example` (`prompt_profile`, `prompt_templates`)

Extra user constraints are appended by `-p/--prompt`.

## Current behavior to remember

- Step 3 output is translation-only (`output_pageXXXX.md`)
- Bilingual merged content is produced at Step 4 (`output.md`)
- `--output-format` is handled in Step 7 (`html` skips conversion)
- `--model` accepts aliases (`pro|flash|lite`) and full model names
- Step 3 model selection:
  1. Chunk size (if thresholds configured) → ModelSelector
  2. CLI --model parameter override
  3. Alias resolution (pro → gemini-3-pro-preview)
  4. Probe availability check (test if model accessible)
  5. Fallback chain (try alternatives if requested unavailable)
- CI quality gate uses workflow `lint-and-test` with blocking lint -> test sequencing (see `docs/architecture/specs/SPEC-003-lint-quality-gates.md`)

## Dev verification

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
bash -n translatebook.sh
uv run python -m py_compile 03_translate_md.py ai/gemini_provider.py ai/model_probe.py 05_md_to_html.py 07_generate_formats.py
```

## Acknowledgements

BookWeaver is reworked from:
https://github.com/wizlijun/claude_translater
