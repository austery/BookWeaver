# ADR-0005: A whole-book term scan runs only when a person asks

Status: Accepted (2026-11-09). The owner approved it by merging PR 77.

## Context

Terms are the project's core difficulty. Extraction can read the book's index, or it can send the whole book (Deep Scan). SPEC-015 required an explicit request for Deep Scan. On 2026-04-07 the code removed the middle tier and made automatic extraction fall back to Deep Scan. That change records why the tier went, but not why the fallback was acceptable: Reason not recorded.

## Decision

Automatic extraction stops with an error when a book has no usable index, before any model call. Deep Scan runs only on explicit request. The heuristic middle tier stays retired.

## Reason

- Owner, 2026-11-09: a Deep Scan uses many tokens, and it has not been tested on a subscription tool.
- "the CLI must never trigger a whole-book high-token extraction call automatically, because that creates surprise API cost." (SPEC-015)
- Middle tier: "Tier 2 heuristics produced 90%+ false positives (sentence-initial caps), completely missed lowercase scientific terms" (commit 3b745f1).

## Alternatives

Keep the automatic fallback. This needs fewer steps for a book with no index, and Deep Scan may give the best terms. Rejected for now, because its cost and capacity are unmeasured.

## Consequences

A book with no index needs one more choice from the person. Revisit this decision when issue #71 has live Deep Scan evidence.
