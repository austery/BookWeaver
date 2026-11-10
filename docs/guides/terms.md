# Terms

How a run chooses the book's key terms, how you supply your own, and how several models can choose them together.

## Term extraction

Before the first translation batch, a run extracts the book's key terms and uses them for the whole book. The upload uses the `pro` profile for this step by default, even when the preset is a `flash` one, so the step draws on Pro quota. The owner's earlier tests found Pro better at this step, so `flash` can lower the quality of the terms. The log names the model that the step uses.

The extraction prompt asks for one translation per term and puts other acceptable ones in a separate `alternatives` field. If a translation still contains a slash, the log names the term and the glossary stays as it is, because a slash can also belong to one translation. After an EPUB run with a glossary, `term-consistency.json` in the checkpoint directory shows how each term was translated. It is a signal, not a verdict: a plural source form is not matched, a sound rewording counts as missing, and a part of a compound translation can count as another option.

Automatic extraction reads the book's back-of-book index and table of contents. If the book has no usable index, the run stops before it calls a model, and the log names the choices. To continue, choose one of these:

- Set `glossary_mode` to `deep-scan` on the upload, or pass `--glossary-mode deep-scan` on the CLI. This sends the whole book in one request, which can use much more quota. It has no live evidence on any subscription CLI yet (issue #71).
- Supply terms with `--glossary PATH` on the CLI.

Choose the model with `extraction_model` on the upload or `--extraction-model` on the CLI. Without the CLI flag, `POST /runs` and the CLI use `terminology_extraction.extraction_model` from the configuration. Different terms change the prompt, so a saved run does not resume with another model's terms.

## Your own glossary and tiers

Supply terms with `--glossary PATH`. A term in a glossary you supply can carry `"tier": "fixed"` or `"tier": "preferred"` (SPEC-028). A fixed term, and any term without a tier, must always use its translation. A preferred term is a suggestion: the prompt lists it in a separate block with its `alternatives`, and the model may use a better fitting translation in a sentence. `term-consistency.json` then counts only fixed drift as inconsistent and reports preferred variation as `preferred_varied`. A glossary with no tier anywhere produces exactly the prompt it produced before, so saved books resume unchanged. Term extraction does not write tiers yet.

## Term Panel (several models choose the terms)

`bookweaver terms BOOK.epub --panel NAME` lets models from different vendors propose and judge the book's terms, then writes a tiered glossary (SPEC-028). It translates nothing; translate afterwards with `--glossary PATH`, using the path it prints. Define panels by name in your configuration, for example:

```json
"terminology_panels": {
  "three-vendor": {
    "nominators": ["agy-flash-low", "codex-gpt-6.1-sol-low", "claude-opus-5-5-low"],
    "judges": ["codex-gpt-6.1-sol-low", "claude-opus-5-5-low"]
  }
}
```

- Each vendor (Google, OpenAI, Anthropic) casts one vote; two presets of one vendor in one list are refused.
- Before any model call the command prints the plan and checks every member's CLI: login where the CLI reports it (Codex, Claude Code), version, and the model list where the CLI has one.
- The glossary and `term-panel-report.json` (votes, tiers, judge bias) are cached in `.bookweaver_glossaries/panel/` in the book folder; a rerun with the same panel makes no call, and a run stopped by one member reuses the other members' replies.
- It needs a book with an index. Paid presets and Deep Scan are not supported in a panel yet.

To choose the terms and translate in one command, pass `--term-panel NAME` to the translate command:

```bash
uv run bookweaver BOOK.epub --output OUT.epub --preset agy-flash-low --term-panel three-vendor
```

- It uses the same cache as `bookweaver terms` (beside the EPUB), so a glossary that command already wrote is reused with no model call.
- It replaces term extraction: it cannot be combined with `--glossary`, `--extraction-model` or `--extract-glossary`, and it overrides `terminology_extraction.enabled` in the configuration.
- The run's audit file (`.bookweaver_runs/<run_id>.json`) names the panel and its members in `term_panel`.
- The local API upload does not offer a panel yet (issue 100, SPEC-028 Phase 4).

## Switching off a subscription

If you no longer have a subscription, list its runtime in your configuration:

```json
"runtimes": {"disabled": ["codex"]}
```

The names are `antigravity`, `codex`, `claude-code`, `gemini`, `openai` and `anthropic`. The runtime's presets then leave `GET /presets`, show `disabled` in `bookweaver presets`, and any run that must call one stops before the call. Remove the runtime from your panels as well. A book whose panel glossary is already cached still resumes.
