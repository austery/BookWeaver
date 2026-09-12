# Application module depth delivery ledger

Contract: [SPEC-022](../architecture/specs/SPEC-022-application-module-depth.md). Base: `ee2e8d7934661b7d9cff78f4456cf3411cda3036`.

| Ticket | Scope | Status |
| --- | --- | --- |
| T1 | [Migrate current application behavior coverage](https://github.com/austery/BookWeaver/issues/27) | Planned |
| T2 | [Declare invocation audit and runtime provenance interface](https://github.com/austery/BookWeaver/issues/28) | Planned |
| T3 | [Resolve prompt preparation before external work](https://github.com/austery/BookWeaver/issues/29) | Planned |
| T4 | [Simplify EPUB source interface and enforce dependencies](https://github.com/austery/BookWeaver/issues/30) | Planned |

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
