# Wayfinder Map: BookWeaver Runtime Convergence

Label: `wayfinder:map`

## Destination

Produce an owner-approved target architecture and staged refactor route that converges BookWeaver on one Supported Product Path: EPUB-to-EPUB through `bookweaver`, with Antigravity as the subscription runtime, explicitly authorized Gemini API execution, and durable segment-level resume.

Markdown and PDF remain Isolated Format Capabilities that can be reintroduced without constraining the supported EPUB design. DOCX and the legacy shell orchestration receive no new compatibility commitment. Reaching the destination means all architectural and migration decisions are resolved and ready to become specifications and an implementation plan; implementation is not part of this map.

## Notes

- Planning only: decision tickets produce decisions, not implementation deliverables.
- Preserve the working hexagonal core unless a ticket demonstrates that an existing seam cannot support the destination.
- Treat `uv run bookweaver` as the canonical product entry point.
- Preserve completed EPUB translations across interruption and explicitly authorized provider changes.
- Technical API availability never authorizes metered token usage.
- Use `codebase-design` vocabulary when placing module seams and evaluating depth.
- Use `domain-modeling` for product terms and hard-to-reverse domain decisions.
- Ground provider, checkpoint, and migration decisions in `docs/architecture/specs/SPEC-020-antigravity-cli-migration-and-paid-api-authorization.md` and its external reviews.

## Decisions so far

<!-- Closed ticket decisions are appended here as one-line context pointers. -->

## Not yet specified

- Exact target package layout after the canonical application seam is chosen.
- Whether the public CLI command shape needs simplification beyond removing unsupported options.
- How configuration is represented after model profiles, paid execution policy, and isolated formats are separated.
- The exact release and deprecation sequence for legacy entry points.
- Which live smoke tests are required at each migration gate without incurring unauthorized API cost.
- Whether future Markdown or PDF support reuses the isolated adapters directly or introduces new adapters against the final application seam.

## Out of scope

- Implementing the refactor while charting this map.
- Restoring DOCX as a supported format.
- Providing full product guarantees for Markdown or PDF in this effort.
- Adding a GUI, billing dashboard, persistent spending authorization, or automatic paid-provider fallback.
- Rewriting the working EPUB parser, patcher, or batching behavior without evidence that the destination requires it.
