---
specId: SPEC-023
title: Installed Runtime Configuration
status: Ready for Implementation
implementationStatus: Locally verified; pending PR merge
priority: P2 - Reliability
creationDate: 2026-09-12
lastUpdateDate: 2026-09-12
relatedSpecs: [SPEC-021, SPEC-022]
---

# SPEC-023: Installed Runtime Configuration

## Goal and evidence

Make the packaged CLI validate configuration without relying on a source checkout. At merged base `2828fa9bf186189449c59d71c41bb03e21ae3299`, the wheel contains no schema; isolated `validate_config({})` fails with FileNotFoundError for `config/schemas/config_schema.json`. Prior package construction and source-tree tests did not cover installed runtime behavior.

The owner authorized advancing the next task after SPEC-022. This is a bounded continuation of SPEC-021's CLI/config acceptance, not whole-book acceptance or legacy retirement. No live model work is required or authorized.

## Decisions

- Move the canonical schema into the `ai` package as `ai/config_schema.json`, declare it as package data, and read it with `importlib.resources`. Keep one source of truth instead of duplicating schema files or depending on wheel installation layout. Update current contributor and README pointers; preserve historical reports as historical evidence.
- Preserve source-checkout configuration layering: checkout `config/config.json`, then user `~/.config/bookweaver/config.json`. Only recognize checkout configuration beside a BookWeaver `pyproject.toml`; do not treat an installed environment's sibling `config/config.json` or the working directory as project configuration. An installed CLI uses the user configuration location. This removes an accidental site-packages lookup without introducing a new config search path.
- Retain strict validation, legacy-path rejection, fixed model/effort behavior, and no implicit paid authorization. Never rewrite user configuration.
- Add a reusable offline installed-artifact smoke test: build sdist, build wheel from sdist, install wheel in an isolated environment, run from outside the checkout, validate configurations, and exercise the actual console command using a bibliography-only EPUB (zero translatable segments). Verify zero Provider/SDK construction and source/output resource preservation. Test project/user precedence separately through the config loader.

## Ticket and acceptance

One delivery ticket: package runtime schema and verify installed CLI/config behavior.

- [x] Schema is present in both sdist and wheel, with unchanged schema content.
- [x] Installed valid config succeeds; unknown keys, invalid values, and legacy config fail before runtime construction.
- [x] Checkout layering is preserved; installed lookup ignores unrelated working-directory and installation-sibling configuration.
- [x] Installed console invocation rebuilds a source-only EPUB with zero Provider construction; invalid configuration preserves an existing destination.
- [x] CI runs the installed-artifact smoke without model calls or external books.
- [x] Full offline test suite, Ruff, Tach, package build, and independent review pass; publish a task-owned PR, do not merge without approval.

## Limits

This covers configuration and zero-work installed execution. It does not certify live translation, glossary model work, visual/semantic book quality, or every remaining SPEC-021 CLI/config requirement.


## Delivery evidence

Ticket: [#33](https://github.com/austery/BookWeaver/issues/33). Implementation head: `245a45a59d5709bacfc8ce922071f28391437b6c`. [Independent review](../../../pr-reviews/installed-runtime-v1.md): zero findings on both Standards and Spec axes.

- Full suite: **624 passed, zero skipped**, in 166.54s, with the local EPUB extraction opt-in enabled. No model calls.
- Ruff lint and format (112 files), Tach, and diff whitespace checks passed.
- Built sdist and wheel from that sdist; both contain the unchanged canonical schema. Installed smoke passed with zero Provider constructions, unchanged source-only EPUB entries, config rejection, and destination preservation.
- Local sandbox could not write the global uv cache or download dependencies. Validation reused an isolated copy of the previously synced environment; all 46 installed non-project dependency versions matched the unchanged lockfile. Building used cached setuptools 82.0.1, `uv build --offline --no-build-isolation`, and a temporary writable cache. CI uses ordinary `uv sync --frozen` and `uv build`.
- The first full run had **6 failed, 618 passed** because the historical shell attempted to initialize its missing legacy environment and download dependencies. Reusing the existing legacy environment fixed the setup: all 17 shell compatibility tests passed, followed by the green full run above. No historical implementation was changed or test skipped.

The installed smoke shares only locked dependency packages with the caller environment and independently rejects importing BookWeaver from outside its installation. It is not a fresh dependency-resolution test, live runtime certification, or whole-book acceptance. Merge remains subject to owner approval.
