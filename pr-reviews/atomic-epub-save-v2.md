# Atomic EPUB save review v2

Reviewed delta: `1721a29120a9c2840f2e81c3a52b987c31385270...bf86e87f7fdcc977a8a9a5e1666fab12b7af26d4`.
Approved requirements: `docs/plans/2026-09-19-atomic-epub-save.md`.
This report supersedes v1's no-remaining-findings conclusion for the earlier head.

| Review item | Evidence | Decision | Resolution |
| --- | --- | --- | --- |
| F1: ZIP or temporary-stream close masks the primary write/sync failure | Both added dual-fault tests fail on 1721a29; standalone close failures already abort | Accept | Preserve the active exception across resource closure; annotate secondary close failures. A close-only error still aborts before replacement. |
| F2: interrupted directory synchronization omits published state | A real SIGINT on 1721a29 raises KeyboardInterrupt without the required diagnostic | Accept | Preserve the interruption and add an output-replaced/durability-unconfirmed note; no rollback. |

## Evidence

- New tests on the original implementation: 3 failed, 19 passed. Failures are exactly the two dual-fault paths and the missing SIGINT diagnostic.
- Fixed implementation: 22 adapter tests passed, including standalone closure failures, primary exception identity, real SIGINT, old/source bytes, and temporary-file cleanup.
- Ruff lint/format, Tach, and diff whitespace checks passed.
- Offline sdist/wheel build and installed-runtime smoke passed with zero provider constructions.
- Existing project dependency environment reused with `uv run --no-sync`; validated legacy shell environment linked into the isolated checkout. No dependency changes or fabricated installation markers.
- No live model calls, book transmission, whole-book acceptance, or merge.

## Spec

Independent review at bf86e87: F1 and F2 resolved; no missing requirements, scope expansion, or incorrect implementation found. Reviewer independently ran all 22 adapter tests, including real SIGINT.

## Standards

Independent review at bf86e87: zero hard violations and zero actionable heuristic findings. The typed close guard concentrates the same error-preservation policy across resource types. Reviewer independently ran all 22 adapter tests.

## Final parent validation

Full suite on the corrected implementation: **640 passed, zero skips**, in 169.00 seconds. This is one complete invocation, including the legacy shell compatibility cases.
