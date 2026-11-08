# BookWeaver contributor notes

## Current product boundary

- Canonical command: `uv run bookweaver`, entry point `ai/cli.py`.
- Application composition: `ai/orchestration.py` and format-specific translation functions.
- Supported format: EPUB-to-EPUB, alternating bilingual text. Table cells and conservatively recognized dedicated bibliography documents remain source-only.
- Active EPUB batch default: 60,000 characters and 200 segments; CLI `--max-batch-segments` overrides `epub_resilience.max_batch_segments`. Generic/legacy batchers retain an optional unbounded default.
- Active EPUB segmenter: `epub-leaf-block-v4-source-only-bibliography`; v3 checkpoint reuse is a hard mismatch. Segment-cap changes alone are soft mismatches; historical missing caps mean unbounded.
- Default runtime: Antigravity through `ai/antigravity_provider.py`; model versions are centralized in `ai/model_profiles.py`.
- Default selection: Flash 3.8 Low. Model and effort are separate user axes; only named rows in `ai/model_profiles.py` `_CLI_ROWS` are enabled (SPEC-025 §3.8), and anything else fails loudly. Pro is `gemini-4-argon`, status `experiment`. `bookweaver rows` lists these CLI rows plus the metered API rows pinned in `_API_MODELS`; `--row NAME` replaces `--model`/`--effort`/`--provider` and cannot be mixed with them (SPEC-026 Phase 1). `uv run bookweaver serve` starts the local API on `127.0.0.1:8765` (`/docs`, `GET /rows`, and `POST /runs/upload`, `POST /runs`, `GET /runs/current`, `POST /runs/current/stop`, which run the CLI as a child process, one run at a time; run record in `$XDG_STATE_HOME/bookweaver/current-run.json`; uploaded books in `~/Documents/BookWeaver/<book name>/`); it needs the optional `api` extra, which the dev group already installs (SPEC-026 §7.3).
- Antigravity version gate: `CERTIFIED_AGY_MODELS` seeds `(agy version, model)` pairs with probe evidence. Any other pair runs a synthetic three-passage probe per framing protocol before its first book batch; passes are recorded in `$XDG_STATE_HOME/bookweaver/runtime-certifications.json` (default `~/.local/state/bookweaver/`). To re-probe, delete the matching entry.
- Paid API construction is authorization-gated by `ai/runtime_factory.py`. Metered providers (`gemini`, `anthropic`, `openai`) share one any-llm adapter there (SPEC-024); pinned models live in `ai/model_profiles.py`. No automatic paid fallback. No live API tests without separate authorization.
- Runtime JSON validation: `ai/runtime_config.py`, `ai/config_schema.json`. Never automatically overwrite ignored user configuration.
- Checkpoint: `ai/checkpoint_store.py`, single atomic schema-v2 document, exclusive run lock, explicit mismatch failures, legacy import without rewriting v1 files.

## Migration status

SPEC-021 is approved for implementation. The new application path and CLI wiring exist, but the migration is not yet fully accepted. One narrative book has complete execution and interruption evidence, plus a selected-chapter fidelity revision. Complete reader/layout acceptance, additional books, full CLI/config coverage, and legacy retirement remain outstanding. Historical helper functions still in `ai/orchestration.py` serve legacy tests and are pending deletion; do not extend them or mistake them for the new application path.

`translatebook.sh`, numbered Markdown scripts, Gemini CLI modules, and the orphaned `ai/epub_translate_roundtrip.py` remain retirement candidates. Do not resurrect or route the new application through them. Keep `08_epub_roundtrip_baseline.py`, EPUB package handling, isolated Markdown/PDF adapters, and evaluation assets.

## Documents

Before publishing a PR that closes a task, follow the task closeout in `~/Documents/global-skills/agents/DOC-LIFECYCLE.md`. Archive: `docs/_archive/`. Link check: `uv run python scripts/check_doc_links.py`. ADRs live in `docs/architecture/decisions/`, a Structure path.

## Verification

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run tach check
uv run python scripts/check_doc_links.py
```

Test behavior through the application, provider, and checkpoint boundaries. Record live probes separately from mocked tests. A tiny EPUB or a passing registry test is not proof of whole-book translation quality. See `docs/architecture/specs/SPEC-021-runtime-convergence-and-book-validation.md` and `docs/plans/2026-09-07-antigravity-protocol-probe.md`.

Current book evidence: `docs/plans/2026-09-07-stoic-joy-book-validation.md` and `docs/plans/2026-09-07-book-quality-polish.md`. Preserve original checkpoints when rebuilding editorial revisions; record reused, retranslated, and manually edited provenance separately. Codex comparison is deferred.
