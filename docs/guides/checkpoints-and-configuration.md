# Checkpoints, batches and configuration

How a run saves progress and resumes, how batches are sized, and where configuration lives.

## Checkpoints

Each successfully validated batch saves accumulated translations and provenance to one atomically replaced `checkpoint.json`. One run owns its checkpoint lock at a time. A failed batch leaves earlier saved work reusable. Resume is enabled by default:

```bash
uv run bookweaver book.epub --output translated.epub
```

Running that command again restores matching segments. A fully restored book is repackaged without further translation calls. Save progress includes checkpoint bytes and elapsed time. Input or segmenter mismatches cannot be forced; language, effort, profile, prompt, or batching changes require explicit `--force-resume`. Concrete model changes produce a continuity warning, except that a resume crossing a Codex or Claude Code model also requires `--force-resume`. Known schema-v1 checkpoints can be imported without rewriting their original files; incompatible or incomplete state stops clearly.

## Batch size and fidelity

Active EPUB runs default to at most 200 segments and 60,000 source characters per batch. The first reached limit closes a batch; an individually oversized segment remains alone for the existing split-retry policy. The segment cap avoids sending hundreds of short notes in one request. Smaller caps add request overhead but reduce work exposed to a failed batch; 200 is an initial operational setting, not a measured optimum.

```bash
uv run bookweaver book.epub --output translated.epub --max-batch-segments 150
```

The CLI overrides `epub_resilience.max_batch_segments` in configuration (positive integer). Character limits remain independently configurable. The generic batcher has no segment cap unless one is supplied.

Each Antigravity batch waits up to 600 seconds for a response by default. Large batches or the Pro profile may need longer; set `antigravity.timeout_seconds` (positive number, at most 86400) in configuration. Codex and Claude Code have the same default, with `codex.timeout_seconds` and `claude_code.timeout_seconds`. A timed-out batch fails without automatic retry or paid fallback; committed batches remain resumable.

Dedicated bibliography pages remain source-only, including their headings. Detection uses bibliography semantics on the XHTML body, or a sole leading heading exactly matching Bibliography, References, Works Cited, or their supported Chinese equivalents. Filenames and prose mentions do not trigger exclusion. Mixed pages with additional headings stay translatable; bibliographies with subsection headings may require future section-level support. Table cells also remain source-only.

For focused review, add instructions with `-p` to preserve numerical ranges, negation scope, possibility versus certainty, and only explicitly stated causes. These are prompting and editorial-review practices, not an automatic semantic correctness guarantee. See the [selected-chapter review and revision ledger](../plans/2026-09-07-book-quality-polish.md).

## Configuration


In a source checkout, runtime configuration is read from checkout `config/config.json`, then `~/.config/bookweaver/config.json` (user values override checkout values). An installed wheel reads only `~/.config/bookweaver/config.json`; neither the working directory nor the installation directory supplies project configuration. The example file is a template, not a runtime default. Configuration is validated against `ai/config_schema.json` before provider construction.

Old model aliases, model probes, fallback settings, output-format settings, and unused legacy controls fail with migration errors. An existing `~/.config/translatebook/config.json` also requires explicit migration. Back up user configuration before changing it. The reference example lists supported settings; model versions belong in the typed registry.

Custom prompt templates are optional. Supply a matching `prompt_profile` and `prompt_templates` mapping; templates may use `{TARGET_LANGUAGE}`, `{GLOSSARY_BLOCK}`, and `{CUSTOM_INSTRUCTIONS_BLOCK}`. Omitting them uses the built-in EPUB prompt.

## Older checkpoints

New EPUB checkpoints and glossary cache keys use a streamed SHA-256 digest of the input file bytes. Identical bytes can resume through the same checkpoint directory after a move or timestamp change; changed bytes cannot resume, even with `--force-resume`. Checkpoint integrity and hard identity fields are checked before automatic glossary extraction.

The source-only bibliography policy uses segmenter `epub-leaf-block-v4-source-only-bibliography`. Older v3 checkpoints, including v1 imports, cannot resume into this policy even with force; preserve them and use a fresh `--checkpoint-dir`. A missing segment-cap field in an otherwise matching checkpoint means the historical unbounded policy; selecting a cap requires explicit force. Changing only the cap is a soft mismatch. The reviewed book is a separately documented reconstruction, not an automatic v3-to-v4 checkpoint migration.

Early schema-v2 checkpoints from PR #25's initial commit used metadata fingerprints. They cannot be reused as content-verified checkpoints: preserve the old directory and choose a fresh `--checkpoint-dir`. Legacy v1 imports require a matching legacy metadata fingerprint plus explicit `--force-resume`; imported segment provenance records `source_verification: legacy_metadata_only`. This acknowledges that historical source bytes cannot be verified from v1 metadata. The original v1 files remain intact.
