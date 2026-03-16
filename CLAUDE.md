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

Translation prompt is defined in:

- `03_translate_md.py` → `create_translation_prompt(...)`

Extra user constraints are appended by `-p/--prompt`.

## Current behavior to remember

- Step 3 output is translation-only (`output_pageXXXX.md`)
- Bilingual merged content is produced at Step 4 (`output.md`)
- `--output-format` is handled in Step 7 (`html` skips conversion)

## Dev verification

```bash
uv run pytest -q
bash -n translatebook.sh
python3 -m py_compile 03_translate_md.py 05_md_to_html.py 07_generate_formats.py
```

## Acknowledgements

BookWeaver is reworked from:
https://github.com/wizlijun/claude_translater
