# ADR-0004: One atomic checkpoint document for each run

Status: Proposed (2026-11-09). Merging this file is the owner's acceptance.

## Context

A whole-book run is long and can be interrupted. Resume must never join translations to metadata from a different state.

## Decision

A run keeps metadata and translations in one document and replaces that document atomically. A mismatch that affects correctness stops the run.

## Reason

"Metadata and translations commit together; simple recovery" (SPEC-021).

## Alternatives

From SPEC-021:

- Two independent files. Rejected: "Can expose mismatched metadata and translations".
- Generation directories with a pointer. Deferred: "More recovery and retention machinery".
- A journal or SQLite. Deferred: "Additional replay/transaction and migration semantics".

## Consequences

Each successful batch rewrites all accumulated state. This cost is accepted until a measurement shows a need to change.
