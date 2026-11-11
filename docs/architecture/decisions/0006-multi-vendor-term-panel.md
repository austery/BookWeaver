# ADR-0006: Multi-vendor terminology panel for candidate nomination and judging

Status: Accepted (2026-11-11). Approved by the owner in conversation.

## Context

Terminology accuracy and consistency are BookWeaver's primary translation difficulty. A single model family can introduce blind spots, idiosyncratic translations, or hallucinated definitions during terminology extraction. Whole-book translation with an ensemble or costly multi-model voting is cost-prohibitive, but terminology extraction operates on a bounded candidate set (TOC and index).

## Decision

Terminology extraction may run as a named Term Panel composed of multiple nominators and judges from different subscription vendors (Claude, Codex, Gemini). The final glossary is synthesized via majority voting rules into tiered terms (`fixed` and `preferred`). The book translation engine itself remains locked to the default subscription translator (Gemini Flash 3.8 Low).

## Reason

- "AI translation's biggest problem is unstable or inaccurate terminology. Different models possess complementary strengths during extraction, but whole-book translation must remain fast, cheap, and consistent." (SPEC-028)
- "Nominators and judges from different vendors balance perspective; majority voting prevents single-vendor hallucination." (SPEC-028 §3.3)
- "Translator remains Gemini 3.8 Flash (`agy-flash-low`); Claude and GPT models nominate and judge terms." (AGENTS.md / North Star)

## Alternatives

- Single-model extraction for all books: keeps the pipeline simple, but leaves domain blind spots. Retained as default single-model path, while panel is available on demand.
- Cross-vendor ensemble for whole-book translation: rejected due to extreme cost, subscription quota exhaustion, and divergent translation styles across chapters.

## Consequences

Running a panel takes longer than single-model extraction and requires active credentials across participating CLI tools. A cached panel glossary is saved beside the EPUB and reused across translation runs.
