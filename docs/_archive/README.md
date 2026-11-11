# Archive

History: specs, plans and other documents whose task has closed. Files here are
moved unchanged with `git mv` and are not maintained; formatters and the link check
skip them. Agents leave this directory out of default reading and search it when
they need to know why something is the way it is.

The rules are in `~/Documents/global-skills/agents/DOC-LIFECYCLE.md` ("Task
closeout"). Add one line per archived file: its original path, the archive date,
and a pointer to its successor (a current document, an ADR, an issue, or "none").

| Archived file | Original path | Archived | Successor |
| --- | --- | --- | --- |
| [SPEC-026](SPEC-026-named-presets-and-local-api.md) | `docs/architecture/specs/SPEC-026-named-presets-and-local-api.md` | 2026-11-08 | `README.md` "Named presets" and "Local API"; `tests/unit/test_local_api.py`; open work: issue #71 |
| [SPEC-001-multi-tier-gemini-translation](SPEC-001-multi-tier-gemini-translation.md) | `docs/architecture/specs/SPEC-001-multi-tier-gemini-translation.md` | 2026-11-09 | `ai/model_profiles.py`; ADR-0001 |
| [SPEC-003-lint-quality-gates](SPEC-003-lint-quality-gates.md) | `docs/architecture/specs/SPEC-003-lint-quality-gates.md` | 2026-11-09 | `pyproject.toml`; `.github/workflows/lint.yml` |
| [SPEC-007-unified-yaml-configuration-governance](SPEC-007-unified-yaml-configuration-governance.md) | `docs/architecture/specs/SPEC-007-unified-yaml-configuration-governance.md` | 2026-11-09 | `ai/runtime_config.py`; `ai/config_schema.json`; SPEC-021 |
| [SPEC-008-epub-block-anchor-redesign](SPEC-008-epub-block-anchor-redesign.md) | `docs/architecture/specs/SPEC-008-epub-block-anchor-redesign.md` | 2026-11-09 | `ai/epub_package.py`; its tests |
| [SPEC-011-model-selection-and-config-abstraction](SPEC-011-model-selection-and-config-abstraction.md) | `docs/architecture/specs/SPEC-011-model-selection-and-config-abstraction.md` | 2026-11-09 | `ai/model_profiles.py`; SPEC-025 |
| [SPEC-012-core-translation-engine-hexagonal](SPEC-012-core-translation-engine-hexagonal.md) | `docs/architecture/specs/SPEC-012-core-translation-engine-hexagonal.md` | 2026-11-09 | `tach.toml`; `tests/unit/test_architecture_contract.py` |
| [SPEC-013-pipeline-completion-shell-replacement](SPEC-013-pipeline-completion-shell-replacement.md) | `docs/architecture/specs/SPEC-013-pipeline-completion-shell-replacement.md` | 2026-11-09 | `uv run bookweaver`; shell retirement: issue #21; format scope: issue #53 |
| [SPEC-014-epub-segment-scaffolding-protocol](SPEC-014-epub-segment-scaffolding-protocol.md) | `docs/architecture/specs/SPEC-014-epub-segment-scaffolding-protocol.md` | 2026-11-09 | `ai/adapters/providers/_delimiter.py`; its tests |
| [SPEC-016-batch-sanity-probe](SPEC-016-batch-sanity-probe.md) | `docs/architecture/specs/SPEC-016-batch-sanity-probe.md` | 2026-11-09 | `tests/unit/test_sanity_observation.py` |
| [SPEC-017-epub-div-extraction-and-cross-doc-batching](SPEC-017-epub-div-extraction-and-cross-doc-batching.md) | `docs/architecture/specs/SPEC-017-epub-div-extraction-and-cross-doc-batching.md` | 2026-11-09 | `ai/epub_package.py`; its tests |
| [SPEC-022-application-module-depth](SPEC-022-application-module-depth.md) | `docs/architecture/specs/SPEC-022-application-module-depth.md` | 2026-11-09 | `ai/orchestration.py`; `tach.toml` |
| [SPEC-023-installed-runtime-config](SPEC-023-installed-runtime-config.md) | `docs/architecture/specs/SPEC-023-installed-runtime-config.md` | 2026-11-09 | `scripts/verify_installed_runtime.py` |
| [SPEC-002-prompt-model-stability](SPEC-002-prompt-model-stability.md) | `docs/architecture/specs/SPEC-002-prompt-model-stability.md` | 2026-11-11 | `ai/core/engine.py`; `tests/unit/test_engine.py` |
| [SPEC-004-baoyu-agent-orchestrated-translation-evaluation](SPEC-004-baoyu-agent-orchestrated-translation-evaluation.md) | `docs/architecture/specs/SPEC-004-baoyu-agent-orchestrated-translation-evaluation.md` | 2026-11-11 | `docs/plans/2026-11-09-translation-evaluation-method.md` |
| [SPEC-005-epub-roundtrip-baseline](SPEC-005-epub-roundtrip-baseline.md) | `docs/architecture/specs/SPEC-005-epub-roundtrip-baseline.md` | 2026-11-11 | `08_epub_roundtrip_baseline.py`; `tests/unit/test_epub_roundtrip.py` |
| [SPEC-006-epub-translate-roundtrip](SPEC-006-epub-translate-roundtrip.md) | `docs/architecture/specs/SPEC-006-epub-translate-roundtrip.md` | 2026-11-11 | `ai/orchestration.py`; `ai/epub_package.py` |
| [SPEC-009-epub-inline-link-preservation](SPEC-009-epub-inline-link-preservation.md) | `docs/architecture/specs/SPEC-009-epub-inline-link-preservation.md` | 2026-11-11 | `ai/epub_package.py`; `tests/unit/test_epub_package.py` |
| [SPEC-010-terminology-extraction-translation-constraints](SPEC-010-terminology-extraction-translation-constraints.md) | `docs/architecture/specs/SPEC-010-terminology-extraction-translation-constraints.md` | 2026-11-11 | `ai/term_extraction.py`; ADR-0005; ADR-0006 |
| [SPEC-015-adaptive-glossary-and-entity-consistency](SPEC-015-adaptive-glossary-and-entity-consistency.md) | `docs/architecture/specs/SPEC-015-adaptive-glossary-and-entity-consistency.md` | 2026-11-11 | `ai/term_extraction.py`; ADR-0005 |
| [SPEC-020-antigravity-cli-migration-and-paid-api-authorization](SPEC-020-antigravity-cli-migration-and-paid-api-authorization.md) | `docs/architecture/specs/SPEC-020-antigravity-cli-migration-and-paid-api-authorization.md` | 2026-11-11 | `ai/adapters/providers/antigravity_provider.py`; ADR-0001; ADR-0002 |
| [SPEC-024-metered-openai-anthropic-providers](SPEC-024-metered-openai-anthropic-providers.md) | `docs/architecture/specs/SPEC-024-metered-openai-anthropic-providers.md` | 2026-11-11 | `ai/runtime_factory.py`; `docs/guides/presets-and-models.md` |
| [SPEC-025-subscription-cli-axis-separation](SPEC-025-subscription-cli-axis-separation.md) | `docs/architecture/specs/SPEC-025-subscription-cli-axis-separation.md` | 2026-11-11 | `ai/model_profiles.py`; ADR-0007; ADR-0008 |
| [2026-03-16-lint-quality-gates-design](2026-03-16-lint-quality-gates-design.md) | `docs/plans/2026-03-16-lint-quality-gates-design.md` | 2026-11-09 | SPEC-003 (archived) |
| [2026-03-16-lint-quality-gates-implementation](2026-03-16-lint-quality-gates-implementation.md) | `docs/plans/2026-03-16-lint-quality-gates-implementation.md` | 2026-11-09 | SPEC-003 (archived) |
| [2026-03-16-prompt-model-stability-design](2026-03-16-prompt-model-stability-design.md) | `docs/plans/2026-03-16-prompt-model-stability-design.md` | 2026-11-11 | SPEC-002 (archived) |
| [2026-03-16-prompt-model-stability-implementation](2026-03-16-prompt-model-stability-implementation.md) | `docs/plans/2026-03-16-prompt-model-stability-implementation.md` | 2026-11-11 | SPEC-002 (archived) |
| [2026-03-17-baoyu-orchestrated-evaluation-design](2026-03-17-baoyu-orchestrated-evaluation-design.md) | `docs/plans/2026-03-17-baoyu-orchestrated-evaluation-design.md` | 2026-11-11 | SPEC-004 (archived) |
| [2026-03-17-baoyu-orchestrated-evaluation-implementation](2026-03-17-baoyu-orchestrated-evaluation-implementation.md) | `docs/plans/2026-03-17-baoyu-orchestrated-evaluation-implementation.md` | 2026-11-11 | SPEC-004 (archived) |
| [2026-03-17-epub-roundtrip-baseline-design](2026-03-17-epub-roundtrip-baseline-design.md) | `docs/plans/2026-03-17-epub-roundtrip-baseline-design.md` | 2026-11-11 | SPEC-005 (archived) |
| [2026-03-17-epub-roundtrip-baseline](2026-03-17-epub-roundtrip-baseline.md) | `docs/plans/2026-03-17-epub-roundtrip-baseline.md` | 2026-11-11 | SPEC-005 (archived) |
| [2026-03-17-epub-translate-roundtrip-design](2026-03-17-epub-translate-roundtrip-design.md) | `docs/plans/2026-03-17-epub-translate-roundtrip-design.md` | 2026-11-11 | SPEC-006 (archived) |
| [2026-03-17-epub-translate-roundtrip](2026-03-17-epub-translate-roundtrip.md) | `docs/plans/2026-03-17-epub-translate-roundtrip.md` | 2026-11-11 | SPEC-006 (archived) |
| [2026-03-18-epub-translate-batch-design](2026-03-18-epub-translate-batch-design.md) | `docs/plans/2026-03-18-epub-translate-batch-design.md` | 2026-11-11 | SPEC-006 (archived) |
| [2026-03-18-epub-translate-batch](2026-03-18-epub-translate-batch.md) | `docs/plans/2026-03-18-epub-translate-batch.md` | 2026-11-11 | SPEC-006 (archived) |
| [2026-03-19-epub-block-anchor-redesign-design](2026-03-19-epub-block-anchor-redesign-design.md) | `docs/plans/2026-03-19-epub-block-anchor-redesign-design.md` | 2026-11-09 | SPEC-008 (archived) |
| [2026-03-19-epub-block-anchor-redesign](2026-03-19-epub-block-anchor-redesign.md) | `docs/plans/2026-03-19-epub-block-anchor-redesign.md` | 2026-11-09 | SPEC-008 (archived) |
| [2026-03-21-dynamic-prompt-refined-minimal-eval-design](2026-03-21-dynamic-prompt-refined-minimal-eval-design.md) | `docs/plans/2026-03-21-dynamic-prompt-refined-minimal-eval-design.md` | 2026-11-11 | `ai/prompting.py` |
| [2026-03-21-dynamic-prompt-refined-minimal-eval-implementation](2026-03-21-dynamic-prompt-refined-minimal-eval-implementation.md) | `docs/plans/2026-03-21-dynamic-prompt-refined-minimal-eval-implementation.md` | 2026-11-11 | `ai/prompting.py` |
| [2026-03-21-pro-timeout-prebatch-design](2026-03-21-pro-timeout-prebatch-design.md) | `docs/plans/2026-03-21-pro-timeout-prebatch-design.md` | 2026-11-11 | `ai/core/engine.py` |
| [2026-03-21-pro-timeout-prebatch-implementation](2026-03-21-pro-timeout-prebatch-implementation.md) | `docs/plans/2026-03-21-pro-timeout-prebatch-implementation.md` | 2026-11-11 | `ai/core/engine.py` |
| [2026-03-21-workflow-default-and-naming-migration](2026-03-21-workflow-default-and-naming-migration.md) | `docs/plans/2026-03-21-workflow-default-and-naming-migration.md` | 2026-11-11 | `uv run bookweaver` |
| [2026-03-21-workflow-naming-and-default-strategy-design](2026-03-21-workflow-naming-and-default-strategy-design.md) | `docs/plans/2026-03-21-workflow-naming-and-default-strategy-design.md` | 2026-11-11 | `uv run bookweaver` |
| [2026-03-25-gemini-cli-resilience-design](2026-03-25-gemini-cli-resilience-design.md) | `docs/plans/2026-03-25-gemini-cli-resilience-design.md` | 2026-11-11 | SPEC-020 (archived) |
| [2026-03-25-gemini-cli-resilience-implementation](2026-03-25-gemini-cli-resilience-implementation.md) | `docs/plans/2026-03-25-gemini-cli-resilience-implementation.md` | 2026-11-11 | SPEC-020 (archived) |
| [2026-04-02-ai-cli-regressions-reliability-plan](2026-04-02-ai-cli-regressions-reliability-plan.md) | `docs/plans/2026-04-02-ai-cli-regressions-reliability-plan.md` | 2026-11-11 | `ai/adapters/providers/` |
| [2026-04-03-chapter1-flash-ab-full-corpus](2026-04-03-chapter1-flash-ab-full-corpus.md) | `docs/plans/2026-04-03-chapter1-flash-ab-full-corpus.md` | 2026-11-11 | `docs/plans/2026-09-07-stoic-joy-book-validation.md` |
| [2026-04-03-chapter1-flash-ab-report](2026-04-03-chapter1-flash-ab-report.md) | `docs/plans/2026-04-03-chapter1-flash-ab-report.md` | 2026-11-11 | `docs/plans/2026-09-07-stoic-joy-book-validation.md` |
| [2026-04-03-chapter2-pro-ab-full-corpus](2026-04-03-chapter2-pro-ab-full-corpus.md) | `docs/plans/2026-04-03-chapter2-pro-ab-full-corpus.md` | 2026-11-11 | `docs/plans/2026-09-07-stoic-joy-book-validation.md` |
| [2026-04-03-python-book-flash-batch-18k-vs-60k](2026-04-03-python-book-flash-batch-18k-vs-60k.md) | `docs/plans/2026-04-03-python-book-flash-batch-18k-vs-60k.md` | 2026-11-11 | `AGENTS.md` (60,000 char default) |
| [2026-04-03-python-book-pro-batch-18k-vs-60k](2026-04-03-python-book-pro-batch-18k-vs-60k.md) | `docs/plans/2026-04-03-python-book-pro-batch-18k-vs-60k.md` | 2026-11-11 | `AGENTS.md` (60,000 char default) |
| [2026-09-12-module-depth-tickets](2026-09-12-module-depth-tickets.md) | `docs/plans/2026-09-12-module-depth-tickets.md` | 2026-11-09 | SPEC-022 (archived) |
| [2026-09-19-atomic-epub-save](2026-09-19-atomic-epub-save.md) | `docs/plans/2026-09-19-atomic-epub-save.md` | 2026-11-09 | `tests/unit/test_adapter_epub_source.py` |
| [superpowers/](superpowers/plans/README.md) | `docs/superpowers/plans/` and `docs/superpowers/specs/` (15 finished AI plans and specs, moved as a batch) | 2026-11-09 | none |
