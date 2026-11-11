# Presets and models

How to choose the model that translates a book, set up each subscription CLI, compare models, and run a paid API.

## Model profiles and effort

The default is Flash 3.8 Low on Antigravity. The public profiles are `flash` and `pro`. Flash supports low, medium, and high effort; Pro supports low and high. Omitted CLI effort means low.

```bash
uv run bookweaver book.epub --output translated.epub --model pro --effort low
```

- Model versions live in `ai/model_profiles.py`. Upgrading a model means changing that registry and verifying the new version. A missing model stops the run; it never switches version silently.
- Medium and high effort still need live acceptance evidence.
- A pair of `agy` version and model with no recorded evidence runs a short automatic check before its first book batch. A model that `agy models` does not list stops the run before that check.
- Add instructions with `-p`. Supply your own terms with `--glossary PATH` (see [Terms](terms.md)).

## Named presets

A preset is a short name for one provider, model profile, and effort. List the enabled presets, with their status and evidence:

```bash
uv run bookweaver presets
```

Use `--preset` in place of `--model`, `--effort`, and `--provider`. You cannot combine them.

```bash
uv run bookweaver book.epub --output translated.epub --preset agy-pro-low
```

Presets that start with `agy-` use the Antigravity subscription, `codex-` presets use the ChatGPT subscription, and `claude-` presets run through Claude Code with your existing `claude` login. A `claude-` run stops unless that login is a claude.ai subscription; one live probe has passed, with no API usage on the account. The `gemini-` and `anthropic-` presets are paid. A preset name does not give consent. Each paid run still needs the [paid API](#paid-api) consent.

Codex presets use their own login, so your Codex rules and skills do not reach a translation. Set it up once:

```bash
mkdir -p ~/.local/state/bookweaver/codex-home
```

```bash
CODEX_HOME=~/.local/state/bookweaver/codex-home codex login
```

## Comparing models

Vendors release new models about every six months, so comparing them is a recurring task. Today, translate the same book once per preset, each into its own output folder, and read the results side by side. Subscription CLIs change often: a new CLI version needs a fresh probe, and a vendor can drop a model from its list. A paid API preset pins one model version in `ai/model_profiles.py`, so it can fit a run that must give stable quality. A benchmark that translates a sample of a book's segments with several presets and prompts is planned in [issue 103](https://github.com/austery/BookWeaver/issues/103). The comparison method and the first evidence for Codex and Claude Code are in the [evaluation record](../plans/2026-11-09-translation-evaluation-method.md); no whole-book comparison has run yet.

## Paid API

CLI failure never automatically switches to an API. The paid presets (`gemini-*`, `anthropic-*`) and their pinned models are listed by `uv run bookweaver presets`. All metered providers share one any-llm adapter ([SPEC-024](../_archive/SPEC-024-metered-openai-anthropic-providers.md)). OpenAI is not pinned yet and fails before any request.

Set the key in the environment: `GEMINI_API_KEY` (or `gemini_api.api_key` in configuration), `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY`.

Paid execution needs your consent for each run: type `USE_API` at the interactive prompt, or pass `--allow-paid-api`:

```bash
uv run bookweaver book.epub --output translated.epub --preset anthropic-flash --allow-paid-api
```

These commands may incur charges. Config files cannot authorize spending. `--provider api` was renamed to `--provider gemini`; existing checkpoints that recorded `api` still resume. Explicit `--effort` is not supported on metered providers (Anthropic is pinned to low effort). Each batch is one streamed request with retries disabled and no engine split retries; reaching the model's output cap stops the run with a suggestion to lower `--max-batch-chars`. `api.timeout_seconds` sets the per-request deadline (default 600). No live paid API test has been performed for these providers.

