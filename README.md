BookWeaver
==========

A TDD-driven translation pipeline for long-form documents (PDF/EPUB/DOCX) that uses the Gemini CLI as the default backend.

Key features
- Multi-tier model selection (automatic per-chunk sizing)
- Bilingual output (alternating format), EPUB-friendly
- Local quota tracking and benchmark tooling
- Designed for zero-interaction batch runs after sample verification

Quick usage

Prerequisites
- gemini CLI (authenticated)
- Calibre (ebook-convert)
- pandoc

Basic dry-run
1. Prepare input file (book.pdf) in working dir.
2. Check environment:
   which gemini || echo "Install and authenticate gemini CLI"
   which ebook-convert || echo "Install Calibre (ebook-convert)"
   which pandoc || echo "Install pandoc"
3. Preview execution plan (no API calls):
   ./translatebook.sh --dry-run book.pdf

Translate (example)
# Full pipeline (convert→translate→merge→html→epub)
./translatebook.sh book.pdf

# Run translation + merge steps only (3-4):
./translatebook.sh --start-step 3 --end-step 4 book.pdf

# Specify model override (e.g., gemini-2.5-flash):
./translatebook.sh --model gemini-2.5-flash book.pdf

# Generate bilingual alternating EPUB:
./translatebook.sh --bilingual-style alternating --output-format epub book.pdf

# Keep HTML only (skip DOCX/EPUB/PDF generation in step 7):
./translatebook.sh --output-format html book.pdf

Configuration
- See config/config.json.example for runtime options and threshold settings (model selection, chunk-size).
- Quota DB: ~/.config/translatebook/quota.db

Notes
- `output_pageXXXX.md` files from step 3 are translated text only.
- Bilingual content appears after step 4 (`output.md`) where source + translation are merged.

Acknowledgements
This project was forked and reworked from https://github.com/wizlijun/claude_translater — many ideas and parts of the original pipeline informed BookWeaver. Thanks to the original author and contributors.

License
MIT - see LICENSE
