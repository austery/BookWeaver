BookWeaver
==========

A TDD-driven translation pipeline for long-form documents (PDF/EPUB/DOCX) that uses the Gemini CLI as the default backend.

Key features
- Multi-tier model selection (automatic per-chunk sizing)
- Bilingual output (alternating / collapsible formats), EPUB-friendly
- Local quota tracking and benchmark tooling
- Designed for zero-interaction batch runs after sample verification

Status
- Early implementation complete: core modules, TDD tests, and scripts are present. See docs/SPEC-001-multi-tier-gemini-translation.md for design details.

Quick start
1. Ensure gemini CLI is installed and authenticated, plus Calibre (ebook-convert) and pandoc.
2. Run: ./translatebook.sh --dry-run <input.pdf>

Acknowledgements
This project was inspired by a previous Claude-based translator — thanks to the original authors for the foundation and ideas.

