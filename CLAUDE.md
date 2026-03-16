# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

**Required environment setup:**
```bash
# ANTHROPIC_API_KEY must be set for Claude API calls
export ANTHROPIC_API_KEY="your-api-key-here"

# Optional: Custom temp directory (default: {filename}_temp)
export CLAUDE_TEMP_DIR="/custom/temp/path"

# Verify installation
python3 --version      # Should be 3.8+
which ebook-convert    # Calibre must be installed
claude --version       # Claude CLI must be authenticated
```

**Tested versions:**
- Python 3.9+
- Calibre 6.0+
- Claude CLI 0.2.0+
- pypandoc 1.11+

### Environment Setup
```bash
# Virtual environment is created automatically by translatebook.sh
# To manually set up for Python script development:
python3 -m venv venv
source venv/bin/activate
pip install python-docx PyMuPDF ebooklib beautifulsoup4 lxml markdown Pillow pdf2image pypandoc
```

## Project Architecture

### High-Level Pipeline (7 Steps)

The translation pipeline follows this sequence:

```
Input File (PDF/DOCX/EPUB/Markdown)
    ↓
[Step 0: Auto-conversion via Calibre HTMLZ]
    ↓ (skips steps 1-2, creates {filename}_temp/ directory)
[Steps 3-4: Translation via Claude API]
    ↓
[Steps 5-7: Format conversion and output]
    ↓
Output (HTML + images, optionally DOCX/EPUB)
```

### Core Components

#### 1. **Main Orchestration**: `translatebook.sh`
- **Role**: Unified entry point for all document translations
- **Key Features**:
  - Auto-detects file format and routes to appropriate converter
  - Manages Python virtual environment (auto-setup, auto-install packages)
  - Handles parameter parsing and validation
  - Supports step-by-step execution or full pipeline
  - Dry-run mode for preview

- **Key Functions**:
  - `setup_venv()`: Creates/activates virtual environment
  - `check_dependencies()`: Validates Python, Claude CLI, Calibre, required scripts
  - `parse_args()`: Parses command-line arguments
  - Main loop: Routes to Calibre conversion, then executes steps 1-7

#### 2. **File Conversion Engine**: `01_convert_to_htmlz.py`
- **Role**: Unified conversion for PDF/DOCX/EPUB → HTML/Markdown
- **Architecture**:
  - Uses Calibre's `ebook-convert` for format normalization
  - Converts any supported format → HTMLZ → extracts HTML + images
  - Applies `pypandoc` to convert HTML → Markdown
  - Implements smart chunking (default 6000 chars) for translation
  - Auto-cleans Calibre markers, page numbers, empty lines

- **Output**: Creates `{filename}_temp/` directory with:
  - `config.txt`: Metadata (input filename, language)
  - `input.html`: Converted HTML
  - `input.md`: Initial markdown
  - `page0001.md` - `pageXXXX.md`: Chunked markdown for translation
  - `images/`: All extracted images

#### 3. **Python Processing Scripts** (Steps 1-7)
Each step is a self-contained Python script:
- **01_prepare_env.py**: Environment setup (legacy, skipped for Calibre conversion)
- **02_split_to_md.py**: File splitting (legacy, skipped for Calibre conversion)
- **03_translate_md.py**: Calls Claude API to translate chunks
- **04_merge_md.py**: Merges translated chunks back into single markdown
- **05_md_to_html.py**: Converts markdown → HTML with styling
- **06_add_toc.py**: Generates table of contents and inserts into HTML
- **07_generate_formats.py**: Optionally creates DOCX/EPUB outputs

#### 4. **HTML-to-EPUB Converter**: `html2epub_simple.sh`
- **Role**: Simple utility to convert final HTML to EPUB format
- **Uses**: pandoc with CSS styling and optional cover image detection

### Temp Directory Structure

For each input file, a `{filename}_temp/` directory is created:
```
book_temp/
├── config.txt          # Metadata: input filename, language settings
├── input.html          # Original converted HTML
├── input.md            # Initial markdown
├── page0001.md         # Chunked markdown blocks (5-8K chars)
├── page0002.md
├── ...
├── output_page0001.md  # Translated chunks (created by step 3)
├── output.md           # Merged translation (created by step 4)
├── book.html           # Final HTML with TOC (created by steps 5-6)
└── images/             # Extracted images (PNG, JPG)
```

**Design Notes**:
- Each step reads/writes specific files in this directory
- `config.txt` ensures multi-project parallelism (step 4-5 use it to find correct temp dir)
- Supports partial re-runs: can restart from any step without losing previous work

### Key Design Decisions

1. **Calibre HTMLZ for Unified Conversion** (v2.0+)
   - **Why**: Solves PDF→Markdown charset corruption issue
   - **Trade-off**: Larger intermediate files, but preserves images and formatting perfectly
   - **Alternative considered**: Direct PDF parsing (lost text encoding, images often corrupted)

2. **Chunking Strategy** (default 6K characters)
   - **Why**: Optimizes Claude API call cost + quality (avoids huge tokens in one call)
   - **Trade-off**: More API calls, but better translation consistency per chunk
   - **Configurable**: Can be tuned via `--chunk-size` in `01_convert_to_htmlz.py`

3. **Temp Directory Naming** (`{filename}_temp`)
   - **Why**: Allows multiple parallel translations of different files
   - **Design**: Metadata in `config.txt` enables steps 4-7 to auto-locate correct dir
   - **Fallback**: If multiple temp dirs exist, uses basename matching + config.txt validation

### Dependency Flow

```
translatebook.sh (bash)
  ├─→ setup_venv() → Python 3 + virtualenv
  ├─→ check_dependencies() → Claude CLI, Calibre, Python scripts
  └─→ 01_convert_to_htmlz.py (for PDF/DOCX/EPUB)
       └─→ Calibre ebook-convert
       └─→ pypandoc
  └─→ 03_translate_md.py
       └─→ Claude CLI (API calls)
  └─→ 04_merge_md.py, 05_md_to_html.py, 06_add_toc.py, 07_generate_formats.py
```

## Important Parameters & Flags

- **`--olang`**: Output language (default: `zh` for Chinese)
- **`--ilang`**: Input language (default: `auto`)
- **`-p, --prompt`**: Custom translation prompt (e.g., domain-specific terms)
- **`--clean`**: Remove temp directory before starting (fresh slate)
- **`--start-step / --end-step`**: Run partial pipeline (1-7)
- **`--dry-run`**: Preview commands without executing
- **`-v, --verbose`**: Detailed output for debugging
- **`--reinstall-packages`**: Force Python package reinstall

## Troubleshooting

### Common Issues

| Problem | Cause | Solution |
|---------|-------|----------|
| "Calibre not found" | Calibre not installed | Install: `brew install --cask calibre` (macOS) or `apt-get install calibre` (Linux) |
| "Claude CLI not found" | Claude CLI not in PATH | Install from https://docs.anthropic.com/en/docs/claude-code |
| "ANTHROPIC_API_KEY not set" | Missing API authentication | `export ANTHROPIC_API_KEY="your-key"` and verify with `claude --version` |
| "Permission denied" on script | Script not executable | `chmod +x translatebook.sh` |
| Multiple temp dirs conflict | Parallel runs on same machine | Each file gets unique temp dir based on basename |
| pypandoc import error | Missing dependency | Run with `--reinstall-packages` flag |
| Conversion produces garbled text | File format issue | Try with `--olang en` to test, check file integrity |
| Large file hangs or timeout | File >100MB or >100 pages | Try `--chunk-size 3000` for smaller chunks, or use `--start-step 3 --end-step 4` to test translation only |
| "Rate limited" from Claude API | Too many concurrent calls | Sequential processing is default; run at most 2-3 parallel translations per machine |

### Debug Tips

```bash
# See what would happen before committing
./translatebook.sh --dry-run book.pdf

# Verbose output to see step-by-step execution
./translatebook.sh -v book.pdf

# Test just the conversion (steps 1-2 equivalent)
python3 01_convert_to_htmlz.py book.pdf

# Check if Calibre is properly installed
which ebook-convert
ebook-convert --version

# Verify Python environment
python3 -c "import pypandoc; print('✓ pypandoc available')"
```

## Code Style & Conventions

- **Language**: Bash (scripts) + Python 3 (processing)
- **Logging**: Color-coded log functions (info, success, warning, error, step)
- **Error Handling**: Explicit exit codes (0=success, 1=error, 2=args, 3=deps, 4=CLI, 5=input-file)
- **Temp Files**: Always stored in `{filename}_temp/`, never scattered in working dir
- **Parameter Passing**: Use `--temp-dir` flag to pass temp location between steps

## Development Workflow

### Testing the Installation

Before translating a real book, verify the full setup works:

```bash
# Create minimal test markdown file
echo -e "# Test Document\n\nHello world. This is a test." > test.md

# Test translation pipeline (steps 3-4 only, fastest)
./translatebook.sh --start-step 3 --end-step 4 test.md

# Verify translation succeeded
cat test_temp/output.md

# Test full pipeline (steps 1-7)
./translatebook.sh test.pdf  # Requires actual PDF file

# Clean up test artifacts
rm -rf test_temp test_temp.md
```

### Modifying the Pipeline

If modifying the pipeline:

1. **Test Calibre conversion**: `python3 01_convert_to_htmlz.py test.pdf --chunk-size 5000`
2. **Validate markdown chunks**: Check `test_temp/page*.md` files are well-formed
3. **Dry-run full pipeline**: `./translatebook.sh --dry-run test.pdf`
4. **Run full translation**: `./translatebook.sh test.pdf`
5. **Inspect output**: Check `test_temp/book.html` for layout issues
6. **Test EPUB generation**: `./html2epub_simple.sh test_temp/book.html`

## Known Limitations & Constraints

- **Concurrent file processing**: Maximum safe parallel runs is 2-3 files per machine (due to Claude API rate limits and disk I/O)
- **Each file isolation**: Each input file gets isolated `{filename}_temp/` directory based on basename
- **Temp directory integrity**: Do not manually modify or delete `{filename}_temp/config.txt` — it tracks translation metadata
- **File size**: Tested up to 500MB; larger files require `--chunk-size 3000` for stability
- **Language support**: Optimized for English → Chinese; other language pairs may require custom `--prompt` tuning
