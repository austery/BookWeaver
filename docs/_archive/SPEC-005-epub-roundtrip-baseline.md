---
specId: SPEC-005
title: EPUB Roundtrip Baseline Mode
status: ✅ 已完成 (Completed)
priority: P1 - Core Feature
creationDate: 2026-03-17
lastUpdateDate: 2026-03-17
owner: Lei Peng (AI-Assisted)
relatedSpecs:
  - SPEC-001
  - SPEC-003
tags:
  - epub
  - baseline
  - roundtrip
  - integrity
---

# SPEC-005: EPUB Roundtrip Baseline Mode

## 1. Goal

> Provide a strict EPUB baseline path that performs zero text mutation while preserving cover semantics, clickable navigation, and package structure fidelity.

## 2. Problem Statement

The translation/render pipeline can intentionally reshape content and layout, which is correct for translation output but unsuitable for structural baseline verification. We need a non-translation control path to compare source EPUB behavior against a rebuilt artifact with minimal packaging changes.

## 3. Baseline Workflow

**CLI entry**: `./translatebook.sh --epub-baseline /path/to/book.epub`

**Execution path**:

1. Parse EPUB package (`META-INF/container.xml` -> OPF).
2. Extract OPF key metadata (`opf_path`, cover item pointer, spine itemrefs).
3. Repack archive to `<temp_dir>/baseline_roundtrip.epub` without mutating content text.
4. Exit early from translation/render/conversion steps.

This keeps baseline and translation flows separated while allowing shared package utilities.

## 4. Integrity Contract

- Cover metadata pointer (`meta name="cover"`) must remain resolvable.
- Navigation references should remain clickable (fragment-link validation available in package utilities).
- Manifest resource references should stay intact (missing asset detection available).
- OPF spine ordering should remain unchanged in baseline roundtrip.

## 5. Acceptance Criteria

- [x] `translatebook.sh` exposes `--epub-baseline`.
- [x] Baseline mode invokes `08_epub_roundtrip_baseline.py` and exits after baseline artifact generation.
- [x] `08_epub_roundtrip_baseline.py` loads package metadata and repacks EPUB.
- [x] Unit tests cover CLI contract and package parser behavior.
- [x] Unit tests cover fragment-link and manifest-asset integrity validators.
- [x] Documentation references baseline command, output path `baseline_roundtrip.epub`, and policy.

## 6. Known Limitations

- Reader engines can still behave differently for non-standard source EPUB quirks even when packaging is valid.
- Current baseline validation utilities are local checks; external `epubcheck` integration is not yet wired as an enforced gate.
- Baseline mode currently targets EPUB inputs only.

## 7. Reader Compatibility Notes

- Baseline mode optimizes for structural preservation rather than reflow normalization.
- If a source EPUB depends on reader-specific quirks, roundtrip output may still differ across readers.
- Compatibility verification should include at least one strict validator and one target reading app.

## 8. Related

- **Entrypoints**: `translatebook.sh`, `08_epub_roundtrip_baseline.py`, `ai/epub_package.py`
- **Tests**: `tests/unit/test_epub_baseline_cli.py`, `tests/unit/test_epub_package_model.py`, `tests/unit/test_epub_integrity_checks.py`
- **Contributor docs**: `README.md`, `CLAUDE.md`
