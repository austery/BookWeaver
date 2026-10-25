# Atomic EPUB save review

Base: `b263ee5fee189b64fcc49f2226dd19290290bbce`.
Implementation reviewed: `428178129c7018a8d90b0703cb2bb53c9f1cd1d1`.
Correction reviewed: `408c2f55969de61487c7705eb815cb9a54e58412`.
Requirements: [approved save contract](../docs/plans/2026-09-19-atomic-epub-save.md).

## Standards

Independent review found no blocking violations. The save interface and ZIP entry processing remain intact, with no generic persistence abstraction or checkpoint changes. Output files inherit the staged file's owner-only mode (`0600`); preservation of an old output's filesystem permissions is not part of this contract.

## Spec

The first independent review reproduced a dual failure: directory fsync failure was masked by descriptor close failure. The correction retains the sync exception as the direct cause and annotates the close failure. Independent re-probing confirmed the fix, with published output still present. No remaining findings.

## Verification

- Both reviewers ran the EPUB adapter suite: 17 passed after the correction.
- Parent first full suite: 633 passed, no skips (before the two additional dual-fault cases).
- Ruff lint, Ruff format, Tach, and diff whitespace checks passed after the correction.
- Rebuilt sdist and wheel; installed CLI/schema smoke passed with zero provider constructions.
- Local checks use the existing project environment via `uv run --no-sync`; the build uses cached setuptools offline. No dependencies or lockfiles changed.
- No live model calls or whole-book/reader acceptance. SPEC-021 remains separate.
- Final full suite after the correction: **635 passed, zero skips**, 166.40 seconds.
