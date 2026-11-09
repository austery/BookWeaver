---
specId: SPEC-013
title: Pipeline Completion — Output Rendering Adapters & Shell Script Replacement
status: 🔵 待办 (Backlog)
priority: P1 - Architecture Completion
creationDate: 2026-04-01
lastUpdateDate: 2026-04-01
owner: Lei Peng (AI-Assisted)
relatedSpecs:
  - SPEC-012
  - SPEC-009
tags:
  - architecture
  - hexagonal
  - shell
  - output-rendering
  - pipeline
  - maintenance
---

# SPEC-013: Pipeline Completion — Output Rendering Adapters & Shell Script Replacement

## 1. Problem Statement

SPEC-012 completed the **translation core** (hexagonal engine + source adapters), but explicitly deferred two items as post-SPEC backlog:

1. **Output rendering is not in `ai/cli.py`**: Steps 5-7 (`05_md_to_html.py`, `06_add_toc.py`, `07_generate_formats.py`) still run as separate scripts orchestrated by `translatebook.sh`. The translation output for non-EPUB paths is raw Markdown — final format conversion (HTML → EPUB/PDF/DOCX) lives entirely in the shell.

2. **`translatebook.sh` is 1,076 lines** and largely untestable. It mixes venv management, argument parsing, dependency checks, step orchestration, and business logic. Adding features, fixing bugs, or onboarding contributors requires reading Bash.

**Net result:** The hexagonal architecture is incomplete. `ai/cli.py` is not a self-contained pipeline — it is a translation-only step that the shell must wrap to produce usable output. The architectural goal of "Python owns the pipeline, shell owns the environment" is not yet realized.

---

## 2. Scope

### In Scope

- **Output rendering adapters** (`IBookSink` port + concrete sinks):
  - `MarkdownBilingualSink` — write bilingual `output.md` (already implicit; needs formalization)
  - `HtmlRenderSink` — run `05_md_to_html.py` logic as a Python callable (Step 5)
  - `TocSink` — run `06_add_toc.py` logic as a Python callable (Step 6)
  - `FormatExportSink` — run `07_generate_formats.py` logic as a Python callable (Step 7); supports `epub | pdf | docx | html`

- **`--output-format` flag in `ai/cli.py`**: wire `epub | pdf | docx | html` to trigger the appropriate sink chain

- **`translatebook.sh` replacement**: reduce shell to a thin environment wrapper (~50 lines):
  - venv creation + package installation
  - `exec python -m ai.cli "$@"` pass-through

- **Input language flag** (`--ilang`): currently parsed by shell but never passed through; add to `ai/cli.py`

### Out of Scope

- DOCX source adapter (deferred; tracked in SPEC-012 backlog)
- HTML source adapter (deferred)
- SPEC-009 inline link preservation (separate SPEC)
- `--quota-status` / `--benchmark` special modes (low priority; keep in shell or drop)

---

## 3. Current Architecture (Gap Diagram)

```
translatebook.sh (1076 lines)
│
├── [venv setup]               ← shell responsibility
├── [arg parsing]              ← duplicated between shell + ai/cli.py
│
├── [EPUB workflow]
│   └── python -m ai.cli       ← ✅ complete (EpubSourceAdapter → EPUB out)
│
└── [Markdown/PDF workflow]
    ├── 01_prepare_env.py      ← input prep (env vars, image extraction)
    ├── 02_split_to_md.py      ← split HTMLZ → page*.md
    ├── python -m ai.cli       ← ✅ translation only (outputs bilingual .md)
    ├── 05_md_to_html.py       ← ❌ NOT in ai/cli.py
    ├── 06_add_toc.py          ← ❌ NOT in ai/cli.py
    └── 07_generate_formats.py ← ❌ NOT in ai/cli.py
```

---

## 4. Target Architecture

```
translatebook.sh (~50 lines)
│
├── [venv setup + package install]
└── exec python -m ai.cli "$@"


ai/cli.py (unified pipeline)
│
├── Source Adapters (existing)
│   ├── EpubSourceAdapter     ← EPUB input
│   ├── PdfSourceAdapter      ← PDF input (Calibre HTMLZ)
│   └── MarkdownSourceAdapter ← pre-split markdown dir
│
├── TranslationEngine (existing)
│
└── Sink Adapters (NEW — IBookSink port)
    ├── EpubSink              ← --output-format epub  (already works for EPUB input)
    ├── HtmlSink              ← --output-format html  (05_md_to_html + 06_add_toc logic)
    ├── EpubFromHtmlSink      ← --output-format epub  (for markdown path: html → epub via 07_generate_formats)
    ├── PdfSink               ← --output-format pdf
    └── DocxSink              ← --output-format docx
```

---

## 5. Implementation Plan

### Phase 1 — Define `IBookSink` Port

```python
# ai/ports/sink.py
class IBookSink(Protocol):
    def write(self, segments: list[BilingualSegment], metadata: BookMetadata) -> Path:
        """Write translated content and return output path."""
        ...
```

### Phase 2 — Migrate Steps 5-7 as Sink Adapters

For each of the three scripts, extract the core logic into a Python callable with no subprocess dependency:

| Script | Target class | Notes |
|--------|-------------|-------|
| `05_md_to_html.py` | `HtmlRenderSink` | bilingual alternating HTML |
| `06_add_toc.py` | `TocSink` | inject `<nav>` TOC |
| `07_generate_formats.py` | `FormatExportSink` | Calibre/ebooklib output |

### Phase 3 — Wire `--output-format` in `ai/cli.py`

```python
# ai/cli.py run()
sink = SinkFactory.create(output_format, output_path, config)
result = engine.translate(source, sink)
```

### Phase 4 — Thin the Shell Script

Replace 1,076-line `translatebook.sh` with a ~50-line wrapper:
```bash
#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Setup venv once
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
fi
source .venv/bin/activate

exec python -m ai.cli "$@"
```

---

## 6. Success Criteria

- [ ] `python -m ai.cli --output-format epub input.pdf` produces a valid bilingual EPUB (no shell needed)
- [ ] `translatebook.sh` is ≤ 100 lines
- [ ] All 365+ existing tests still pass
- [ ] New sink adapter tests: ≥ 15 unit tests covering HTML rendering, TOC injection, format export
- [ ] E2E verified: PDF → EPUB and Markdown → EPUB via `ai/cli.py` only

---

## 7. Open Questions

1. Should `01_prepare_env.py` and `02_split_to_md.py` also be absorbed? They handle input-side splitting — `PdfSourceAdapter` already covers most of this, but image extraction and env var setup may need a migration pass.
2. Should we keep `--quota-status` / `--benchmark` / `--epub-baseline` in the new thin shell, or move them to separate scripts?
3. `--output-format` for EPUB-input path: already works (EpubSourceAdapter outputs EPUB). Should `epub` output from a PDF/Markdown source reuse the same EPUB packaging code?

---

## 8. Why Not Extend SPEC-012?

SPEC-012 is closed and merged. Its scope was the **translation core** (hexagonal engine, source adapters, provider adapters). Output rendering is a distinct concern — it belongs to a separate SPEC so the completion history is clear and the work is independently plannable.
