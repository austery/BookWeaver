BookWeaver
==========

BookWeaver is a document translation pipeline for long books (`.epub`, `.pdf`, `.docx`) using Gemini CLI, with EPUB-first output and bilingual merge support.

## What it does

- Converts input files to markdown chunks
- Translates chunks with Gemini models
- Merges source + translation into bilingual markdown
- Renders HTML and exports final formats (EPUB/DOCX/PDF or HTML-only)

## Quick start

### 1) Prerequisites

- `gemini` CLI (authenticated)
- `ebook-convert` (Calibre)
- `pandoc`

```bash
which gemini
which ebook-convert
which pandoc
```

### 2) Dry-run first

```bash
./translatebook.sh --dry-run /path/to/book.epub
```

### 3) Real run (EPUB preferred)

```bash
# Full pipeline
./translatebook.sh --output-format epub /path/to/book.epub

# Force model for step 3
./translatebook.sh --model gemini-2.5-flash --output-format epub /path/to/book.epub

# HTML only (skip format conversion in step 7)
./translatebook.sh --output-format html /path/to/book.epub
```

### 4) Sample workflow (first 3 chunks)

```bash
python3 01_convert_to_htmlz.py /path/to/book.epub
# prepare a sample temp dir with page0001~page0003.md
python3 03_translate_md.py --temp-dir <sample_temp_dir> --model gemini-2.5-flash --output-lang zh
```

## Pipeline

1. `01_convert_to_htmlz.py` (normalize and split)
2. `03_translate_md.py` (translation)
3. `04_merge_md.py` (bilingual merge)
4. `05_md_to_html.py` (HTML rendering)
5. `06_add_toc.py` (TOC)
6. `07_generate_formats.py` (EPUB/DOCX/PDF generation)

## Prompt definition

The translation prompt is defined in:

- `03_translate_md.py` → `create_translation_prompt(output_lang, custom_prompt=None)`

You can append extra instructions with:

```bash
./translatebook.sh -p "Your custom translation constraints" /path/to/book.epub
```

## Important behavior notes

- Step 3 output files (`output_pageXXXX.md`) are translation-only.
- Bilingual content appears after Step 4 merge (`output.md`).
- `--bilingual-style` currently supports only `alternating`.

## Config

- Runtime config template: `config/config.json.example`
- Quota DB: `~/.config/translatebook/quota.db`

## Acknowledgements

This project was forked and reworked from:
https://github.com/wizlijun/claude_translater

Thanks to the original author and contributors for the foundation.

## License

MIT (see `LICENSE`)
