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
| [2026-03-16-lint-quality-gates-design](2026-03-16-lint-quality-gates-design.md) | `docs/plans/2026-03-16-lint-quality-gates-design.md` | 2026-11-09 | SPEC-003 (archived) |
| [2026-03-16-lint-quality-gates-implementation](2026-03-16-lint-quality-gates-implementation.md) | `docs/plans/2026-03-16-lint-quality-gates-implementation.md` | 2026-11-09 | SPEC-003 (archived) |
| [2026-03-19-epub-block-anchor-redesign-design](2026-03-19-epub-block-anchor-redesign-design.md) | `docs/plans/2026-03-19-epub-block-anchor-redesign-design.md` | 2026-11-09 | SPEC-008 (archived) |
| [2026-03-19-epub-block-anchor-redesign](2026-03-19-epub-block-anchor-redesign.md) | `docs/plans/2026-03-19-epub-block-anchor-redesign.md` | 2026-11-09 | SPEC-008 (archived) |
| [2026-09-12-module-depth-tickets](2026-09-12-module-depth-tickets.md) | `docs/plans/2026-09-12-module-depth-tickets.md` | 2026-11-09 | SPEC-022 (archived) |
| [2026-09-19-atomic-epub-save](2026-09-19-atomic-epub-save.md) | `docs/plans/2026-09-19-atomic-epub-save.md` | 2026-11-09 | `tests/unit/test_adapter_epub_source.py` |
| [superpowers/](superpowers/plans/README.md) | `docs/superpowers/plans/` and `docs/superpowers/specs/` (15 finished AI plans and specs, moved as a batch) | 2026-11-09 | none |
