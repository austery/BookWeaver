# Application module depth review v1

Base: `ee2e8d7934661b7d9cff78f4456cf3411cda3036`.
Reviewed head: `27f5d99c6071f47dd7397249d1b435f262cd8414`.
Contract: SPEC-022; SPEC-021 retains product and retirement authority.

## Standards

One P2 finding: `ai/orchestration.py:362` changes the active model before constructing the translation Provider but retains the glossary Provider until construction succeeds. An independent offline construction-failure probe produced a Flash audit carrying the preceding Pro runtime version. This violates truthful execution evidence. No additional documented-standard violations or blocking heuristic smells were found.

Validation: 19 focused audit/prompt/EPUB/architecture tests passed, plus the independent construction-failure probe. Review was read-only and used no live Provider.

## Spec

Two P2 findings:

1. Mixed audit provenance, including requested effort: translation construction failure borrows the glossary version; glossary failure records the translation-request effort instead of its own default selection. Violates SPEC-022's unavailable-runtime and truthful-evidence requirements. Independently reproduced both cases.
2. CLI usage is reported as zero by aggregating an empty list of paid requests. This predates the refactor but conflicts with SPEC-022's explicit requirement to distinguish unavailable usage from known zero work. Independently reproduced through the default factory.

The remaining inspected test migration, early prompt preparation, real EPUB tests, and forbidden dependency probe matched the contract. Validation: 19 focused tests passed plus independent fault/state probes. No live calls.

## Outcome

Request changes. Standards: one P2; Spec: two P2. The shared provenance finding is intentionally retained in both axes.
