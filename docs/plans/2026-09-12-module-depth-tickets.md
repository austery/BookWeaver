# Application module depth delivery ledger

Contract: [SPEC-022](../architecture/specs/SPEC-022-application-module-depth.md). Base: `ee2e8d7934661b7d9cff78f4456cf3411cda3036`.

| Ticket | Scope | Status |
| --- | --- | --- |
| T1 | [Migrate current application behavior coverage](https://github.com/austery/BookWeaver/issues/27) | Implemented; review resolved |
| T2 | [Declare invocation audit and runtime provenance interface](https://github.com/austery/BookWeaver/issues/28) | Implemented; review resolved |
| T3 | [Resolve prompt preparation before external work](https://github.com/austery/BookWeaver/issues/29) | Implemented; review resolved |
| T4 | [Simplify EPUB source interface and enforce dependencies](https://github.com/austery/BookWeaver/issues/30) | Implemented; review resolved |

## Historical CLI test inventory

Every test class in `tests/unit/test_cli.py` at the base is listed below. Historical tests remain runnable until the SPEC-021 retirement gates pass. They are not a migration acceptance substitute.

| Class | Disposition |
| --- | --- |
| `TestBuildSystemPrompt` | Retained parser/prompt/sanity helper coverage; private helper tests supplement current application tests and do not establish runtime acceptance. |
| `TestSanityProbeConfig` | Retained parser/prompt/sanity helper coverage; private helper tests supplement current application tests and do not establish runtime acceptance. |
| `TestSanityCheckBatch` | Retained parser/prompt/sanity helper coverage; private helper tests supplement current application tests and do not establish runtime acceptance. |
| `TestEmitBatchSample` | Retained parser/prompt/sanity helper coverage; private helper tests supplement current application tests and do not establish runtime acceptance. |
| `TestGlossaryPromptInjection` | Retained parser/prompt/sanity helper coverage; private helper tests supplement current application tests and do not establish runtime acceptance. |
| `TestGlossaryProgressLog` | Retained parser/prompt/sanity helper coverage; private helper tests supplement current application tests and do not establish runtime acceptance. |
| `TestLanguageResolution` | Retained parser/prompt/sanity helper coverage; private helper tests supplement current application tests and do not establish runtime acceptance. |
| `TestLoadConfig` | Historical policy only; strict config, fixed profiles, no fallback, and format isolation supersede these expectations (SPEC-021). |
| `TestCreateProviderResilience` | Historical policy only; strict config, fixed profiles, no fallback, and format isolation supersede these expectations (SPEC-021). |
| `TestCreateProviderCliApiFallback` | Historical policy only; strict config, fixed profiles, no fallback, and format isolation supersede these expectations (SPEC-021). |
| `TestBuildParser` | Retained parser/prompt/sanity helper coverage; private helper tests supplement current application tests and do not establish runtime acceptance. |
| `TestNoSanityProbeFlag` | Retained parser/prompt/sanity helper coverage; private helper tests supplement current application tests and do not establish runtime acceptance. |
| `TestMainModelExplicitness` | Retained parser/prompt/sanity helper coverage; private helper tests supplement current application tests and do not establish runtime acceptance. |
| `TestGlossaryModeParser` | Retained parser/prompt/sanity helper coverage; private helper tests supplement current application tests and do not establish runtime acceptance. |
| `TestGlossaryModeMainForwarding` | Retained parser/prompt/sanity helper coverage; private helper tests supplement current application tests and do not establish runtime acceptance. |
| `TestBuildParserFormatRouting` | Retained parser/prompt/sanity helper coverage; private helper tests supplement current application tests and do not establish runtime acceptance. |
| `TestDetectInputFormat` | Historical policy only; strict config, fixed profiles, no fallback, and format isolation supersede these expectations (SPEC-021). |
| `TestRunInputValidation` | Current behavior covered through test_application_contract.py, test_orchestration.py, and test_review_regressions.py; old automatic model fallback, v1 writes, and isolated glossary warnings remain historical only. |
| `TestRunModelResolutionSemantics` | Current behavior covered through test_application_contract.py, test_orchestration.py, and test_review_regressions.py; old automatic model fallback, v1 writes, and isolated glossary warnings remain historical only. |
| `TestRunGlossaryExtractionOrchestration` | Current behavior covered through test_application_contract.py, test_orchestration.py, and test_review_regressions.py; old automatic model fallback, v1 writes, and isolated glossary warnings remain historical only. |
| `TestRunSanityProbe` | Current behavior covered through test_application_contract.py, test_orchestration.py, and test_review_regressions.py; old automatic model fallback, v1 writes, and isolated glossary warnings remain historical only. |
| `TestRunResumeCheckpoint` | Current behavior covered through test_application_contract.py, test_orchestration.py, and test_review_regressions.py; old automatic model fallback, v1 writes, and isolated glossary warnings remain historical only. |
| `TestRunProgressLogging` | Historical event vocabulary only; active source/checkpoint/done reporting remains in application tests. No promise to preserve old per-stage events. |


## Delivery slices

1. `codex/application-runtime-depth` targets `main`: T1-T3, current application tests, runtime audit, prompt preparation, and review corrections.
2. `codex/deepen-application-modules` targets the first branch: T4, real EPUB Interface tests and explicit Tach dependencies.

The runtime correction at `70998a3` is the same patch as reviewed `661cfa5`. The second branch merges the first so its PR diff contains only the EPUB/dependency slice and final acceptance evidence. Retain both worktrees for feedback. Merge requires owner approval.

Reviews: [v1](../../pr-reviews/module-depth-v1.md), [v2](../../pr-reviews/module-depth-v2.md), [v3](../../pr-reviews/module-depth-v3.md). Both review axes independently verified the corrective audit behavior. No live Provider was called.


## Final validation

| Slice | Source head tested | Evidence |
| --- | --- | --- |
| Runtime/prompt | `3fe584b768ef57c04f19f112559b913a6365866c` | 624 passed in 166.61s; no skips |
| EPUB/dependencies (combined) | `92144e6326f6c74d450829732248e2ad41e4a918` | 618 passed in 167.27s; no skips |

Both runs used `BOOKWEAVER_RUN_EXTERNAL_CASES=1 uv run pytest -q -rs`. The sole normally opt-in case reads a local book chapter and checks 172 extracted segments; it performs no model or network call. Before enabling that case, the baseline was 590 passed/1 skipped, and the first combined implementation run was 612 passed/1 skipped. Intermediate corrected runs were 623 and 617 passed. These are distinct historical runs, not final-head evidence.

Both final slices passed `uv run ruff check .`, `uv run ruff format --check .`, `uv run tach check`, and `uv build` (sdist and wheel). The combined source is identical to the independently reviewed runtime correction plus the previously reviewed EPUB/dependency slice. The only subsequent edits are this acceptance ledger, SPEC status, and review reports. The copied-tree architecture fault test independently rejects a checkpoint-to-application import.

Initial review identified mixed audit provenance and unavailable usage represented as zero. Follow-up review verified both corrections. A further offline paid-request/usage-audit dual-failure test first failed, was repaired, then independently rechecked for RuntimeError, KeyboardInterrupt, and SystemExit; each retained the original identity or cause and one SDK attempt. Both review axes have zero unresolved findings.

## Retained limits

- No live Antigravity or Gemini API calls, no book transmission, and no whole-book quality claim.
- SPEC-021 reader/layout acceptance, additional books, remaining broader CLI/config coverage, and historical runtime retirement remain open.
- Historical scripts and legacy tests are retained. This increment removes obsolete private EPUB test injection hooks, not the historical runtime.
- Build success establishes package construction, not installed-runtime or production acceptance.
- Both PRs and worktrees are retained for review. Merge and destructive cleanup require owner authorization.
