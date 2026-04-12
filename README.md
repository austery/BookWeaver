# BookWeaver (EPUB-First)

BookWeaver is a high-performance, **EPUB-centric** translation engine. It leverages the latest **Gemini 2.5** models to deliver professional-grade bilingual (`alternating`) translations while strictly preserving the eBook's structure, navigation (TOC), and metadata.

> **⚠️ Format Notice:** Support for PDF and DOCX is legacy and experimental. Due to the inherent complexity of these formats, BookWeaver is optimized for **EPUB-to-EPUB** workflows. For the best results, convert your sources to EPUB before translating.

---

## ⚡ Quick Start

### 1. Requirements & Setup
- **Python 3.13+** (Modern runtime for high performance)
- **[uv](https://github.com/astral-sh/uv)** (Recommended package manager)
- **Gemini CLI** (Authenticated) OR **Gemini API Key**

```bash
# Install and synchronize
uv sync
```

### 2. The "Magic" One-Step Command (Recommended)
This is the most efficient way to use BookWeaver. It automatically extracts key terminology, builds a glossary, and translates the entire book in a single pass.

```bash
uv run bookweaver book.epub --output translated.epub --extract-glossary --model pro
```

---

## 💎 Key Features

### 1. Gemini 2.5 Native Support
BookWeaver is hardcoded to use the latest Gemini 2.5 series for superior reasoning and translation quality.

| Alias | Target Model | Best For... |
|---|---|---|
| `pro` | `gemini-2.5-pro` | Technical manuals, complex literature, and terminology extraction. |
| `flash` | `gemini-2.5-flash` | Standard fiction, large books, and quick turnarounds. |
| `lite` | `gemini-2.5-flash-lite` | Extremely fast drafts and high-volume batch processing. |

### 2. Advanced Terminology (Glossary)
BookWeaver's standout feature is its ability to maintain consistency via AI-driven terminology extraction.

- **Unified Flow**: `--extract-glossary` runs both extraction *and* translation in a single session.
- **Priority Filtering**: Use `--glossary-min-priority high` to only inject the most critical terms, keeping prompts lean.
- **Extraction Modes** (`--glossary-mode`):
    - **`auto` (Default)**: Smart and efficient. It targets the book's Index and Table of Contents (TOC). If no index is found (e.g., in a novel), it automatically falls back to `deep-scan`.
    - **`deep-scan`**: Thorough and intensive. It performs a **whole-book analysis** to extract terms from every page. Use this for books without an index or for maximum consistency.

### 3. Resilience & Checkpointing
Built for long-running translations:
- **Resume**: Automatically resumes from the last successful chapter if interrupted.
- **Fallback**: Add `--cli-api-fallback` to switch to the direct API backend if the CLI encountered transient errors.

---

## 🛠 Advanced Usage

### Manual Glossary
If you want to use a custom terminology file:
```bash
uv run bookweaver book.epub --output out.epub --glossary my_terms.json
```

### Sanity Probe
The tool includes an experimental "Sanity Probe" to prevent AI hallucinations or language errors. It is currently **disabled by default** in the standard configuration but can be toggled:
- Enable in `config/config.json` under `sanity_probe.enabled`.
- Disable at runtime with `--no-sanity-probe`.

### Legacy Workflow
For PDF/DOCX, the legacy shell orchestrator is still available (requires Calibre):
```bash
./translatebook.sh --workflow markdown path/to/file.pdf
```

---

## 🧪 Development & Quality
```bash
uv run ruff check .      # High-speed linting
uv run pytest           # Full test suite
```
