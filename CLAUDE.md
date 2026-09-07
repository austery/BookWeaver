# BookWeaver contributor notes

## Current product boundary

- Canonical command: `uv run bookweaver`, entry point `ai/cli.py`.
- Application composition: `ai/orchestration.py` and format-specific translation functions.
- Supported format: EPUB-to-EPUB, alternating bilingual text. Table cells and conservatively recognized dedicated bibliography documents remain source-only.
- Active EPUB batch default: 60,000 characters and 200 segments; CLI `--max-batch-segments` overrides `epub_resilience.max_batch_segments`. Generic/legacy batchers retain an optional unbounded default.
- Active EPUB segmenter: `epub-leaf-block-v4-source-only-bibliography`; v3 checkpoint reuse is a hard mismatch. Segment-cap changes alone are soft mismatches; historical missing caps mean unbounded.
- Default runtime: Antigravity through `ai/antigravity_provider.py`; model versions are centralized in `ai/model_profiles.py`.
- Default selection: Flash 3.8 Low. Model and effort are separate user axes; unsupported combinations fail loudly.
- Paid API construction is authorization-gated by `ai/runtime_factory.py`. No automatic paid fallback. No live API tests without separate authorization.
- Runtime JSON validation: `ai/runtime_config.py`, `config/schemas/config_schema.json`. Never automatically overwrite ignored user configuration.
- Checkpoint: `ai/checkpoint_store.py`, single atomic schema-v2 document, exclusive run lock, explicit mismatch failures, legacy import without rewriting v1 files.

## Migration status

SPEC-021 is approved for implementation. The new application path and CLI wiring exist, but the migration is not yet fully accepted. One narrative book has complete execution and interruption evidence, plus a selected-chapter fidelity revision. Complete reader/layout acceptance, additional books, full CLI/config coverage, and legacy retirement remain outstanding. Historical helper functions still in `ai/orchestration.py` serve legacy tests and are pending deletion; do not extend them or mistake them for the new application path.

`translatebook.sh`, numbered Markdown scripts, Gemini CLI modules, and the orphaned `ai/epub_translate_roundtrip.py` remain retirement candidates. Do not resurrect or route the new application through them. Keep `08_epub_roundtrip_baseline.py`, EPUB package handling, isolated Markdown/PDF adapters, and evaluation assets.

## Verification

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run tach check
```

Test behavior through the application, provider, and checkpoint boundaries. Record live probes separately from mocked tests. A tiny EPUB or a passing registry test is not proof of whole-book translation quality. See `docs/architecture/specs/SPEC-021-runtime-convergence-and-book-validation.md` and `docs/plans/2026-09-07-antigravity-protocol-probe.md`.

Current book evidence: `docs/plans/2026-09-07-stoic-joy-book-validation.md` and `docs/plans/2026-09-07-book-quality-polish.md`. Preserve original checkpoints when rebuilding editorial revisions; record reused, retranslated, and manually edited provenance separately. Codex comparison is deferred.
