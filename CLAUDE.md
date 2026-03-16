# CLAUDE.md (BookWeaver guidance)

This file documents repository-specific conventions and runbook for BookWeaver. It originally accompanied a Claude-based pipeline; the project has been migrated and reworked to use the Gemini CLI as the default model backend. The intent of this file is to help contributors understand architecture, prerequisites, and how to run the pipeline locally.

## BookWeaver Phase 1 Status (Gemini Migration)

- `03_translate_md.py` uses Gemini CLI via `ai/gemini_provider.py`
- Dynamic model routing is in `ai/model_selector.py`
- Step 4/5 bilingual path is enabled:
  - `04_merge_md.py` merges original + translated chunks
  - `05_md_to_html.py` renders alternating bilingual HTML
- Quota tracking uses SQLite in `ai/quota_tracker.py`
- Benchmark helper: `benchmark_models.py`

### New translatebook.sh parameters

```bash
./translatebook.sh --model gemini-2.5-flash book.pdf
./translatebook.sh --sample-only book.pdf
./translatebook.sh --benchmark book.pdf
./translatebook.sh --quota-status book.pdf
./translatebook.sh --output-format epub --bilingual-style alternating book.pdf
```

## Quick Start Commands

### Main Translation Tool
```bash
# Basic translation (auto-detects file format)
./translatebook.sh book.pdf
./translatebook.sh document.docx
./translatebook.sh ebook.epub

# Translate with custom language output
./translatebook.sh --olang en book.pdf

# Translate with custom prompt
./translatebook.sh -p "Your custom translation prompt here" book.pdf

# Clean temp directory and translate
./translatebook.sh --clean -v book.pdf

# Preview what would happen (dry-run)
./translatebook.sh --dry-run book.pdf

# Run specific steps only (e.g., steps 3-4 for translation)
./translatebook.sh --start-step 3 --end-step 4 book.pdf

# Show help with all options
./translatebook.sh -h
```

### Standalone Conversion
```bash
# Convert document to HTML/Markdown chunks (new unified approach)
python3 01_convert_to_htmlz.py book.pdf
python3 01_convert_to_htmlz.py document.docx --chunk-size 5000

# Simple HTML to EPUB conversion
./html2epub_simple.sh input.html output.epub
```

### Prerequisites & Environment Variables

**Required tools:**
```bash
# Gemini CLI (ensure installed and authenticated)
which gemini || echo "Install and authenticate gemini CLI"
# Calibre (ebook-convert)
which ebook-convert || echo "Install Calibre (ebook-convert)"
# pandoc
which pandoc || echo "Install pandoc"
```

**Tested versions:**
- Python 3.9+
- Calibre 6.0+
- pandoc recent stable
- gemini CLI available in PATH and authenticated

## Environment Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install python-docx PyMuPDF ebooklib beautifulsoup4 lxml markdown Pillow pdf2image pypandoc
```

## Project Architecture (summary)

The translation pipeline follows this sequence:

```
Input File (PDF/DOCX/EPUB/Markdown)
    ↓
[Step 0: Auto-conversion via Calibre HTMLZ]
    ↓
[Steps 3-4: Translation via Gemini CLI]
    ↓
[Steps 5-7: Format conversion and output]
    ↓
Output (HTML + images, optionally DOCX/EPUB)
```

## Notes about migration from the original Claude-based project

This repository is a rework of an earlier Claude-based translator. Where relevant, code and ideas were adapted from that work; however the runtime model backend is Gemini CLI. Contributors should prefer the new Gemini-based codepaths and follow the TDD process described in the project.

## Acknowledgements
This project was forked and reworked from https://github.com/wizlijun/claude_translater — many ideas and parts of the original pipeline informed BookWeaver. Thanks to the original author and contributors.

