---
specId: SPEC-006
title: EPUB Translate Roundtrip Mode
status: ✅ 已完成 (Completed)
priority: P1 - Core Feature
creationDate: 2026-03-17
lastUpdateDate: 2026-03-17
owner: Lei Peng (AI-Assisted)
relatedSpecs:
  - SPEC-005
  - SPEC-003
tags:
  - epub
  - translation
  - roundtrip
  - integrity
---

# SPEC-006: EPUB Translate Roundtrip Mode

## 1. Goal

> Provide an optional package-aware EPUB translation mode that produces bilingual alternating output while preserving source package structure and enforcing strict integrity validation.

## 2. Problem Statement

The default markdown-render-convert translation pipeline is effective for general output, but it can alter structure and navigation behavior compared with source EPUB packaging. We need a flag-gated path that translates in-package XHTML content directly and repacks with fidelity checks.

## 3. CLI and Workflow

**CLI entry**:

```bash
./translatebook.sh --epub-translate-roundtrip --olang zh /path/to/book.epub
```

**Execution path**:

1. Load source EPUB package model.
2. Select translatable spine XHTML documents.
3. Extract body text segments and translate via Gemini CLI.
4. Batch segments per document using `%%` separators and parse translated output with strict segment-count checks.
5. If segment counts mismatch, retry with binary split sub-batches until aligned or fail.
6. Patch source XHTML with alternating bilingual text.
7. Validate package structure, fragment links, and asset references strictly.
8. Repack to `<temp_dir>/translated_roundtrip.epub`.
9. Exit without running legacy step-based markdown pipeline.

## 4. Integrity and Failure Policy

Strict fail-fast contract:

- Any broken cover/toc/spine pointer -> fail non-zero.
- Any missing manifest asset -> fail non-zero.
- Any broken internal fragment link -> fail non-zero.
- No warning-only continuation.

## 5. Scope (Phase 1)

- Supported bilingual style: `alternating` only.
- nav/toc resources are preserved (not translated in this phase).
- Resource paths and OPF ordering remain unchanged.
- Mode is opt-in via `--epub-translate-roundtrip`; default workflow remains unchanged.
- Model fallback chain is out of scope for this phase.

## 6. Acceptance Criteria

- [x] `translatebook.sh` exposes and wires `--epub-translate-roundtrip`.
- [x] `09_epub_translate_roundtrip.py` executes package-aware translate flow.
- [x] Unit tests cover CLI contract, alternating patching, and workflow integrity behavior.
- [x] Batch translation parser/retry tests cover `%%` alignment and split retry behavior.
- [x] Output EPUB is generated as `<temp_dir>/translated_roundtrip.epub`.
- [x] Repository quality gates pass (`ruff`, `pytest`, shell syntax, py_compile).

## 7. E2E Validation Checklist

- Cover renders correctly in target reader.
- TOC entries remain clickable.
- Anchor jumps resolve in translated EPUB.
- No missing image/css/font resources.
- Alternating bilingual text appears in translated spine content.

## 8. Related

- **Entrypoints**: `translatebook.sh`, `09_epub_translate_roundtrip.py`, `ai/epub_translate_roundtrip.py`
- **Utilities**: `ai/epub_package.py`
- **Tests**: `tests/unit/test_epub_baseline_cli.py`, `tests/unit/test_epub_translate_patcher.py`, `tests/unit/test_epub_translate_roundtrip.py`

## 9. External Reference

- Immersive Translate `1.26.6` is used as a translation UX/prompt reference point, especially for paragraph-structure-preserving translation output expectations.
