# Baoyu Workflow Alignment Design

## Goal

Align BookWeaver orchestrated mode with the `baoyu-translate` workflow so prompt generation is analysis-driven (not a short static template), and can run in a prompt-only phase before translation.

## Why current behavior is wrong

Current `ai/orchestrator.py` writes a short `02-prompt.md` with fixed sections and does not materialize the full context structure described by baoyu references:

- preferences and glossary merge
- analysis-driven context assembly
- comprehension challenges
- metaphor/figurative strategy mapping

As a result, `02-prompt.md` is too shallow and does not justify orchestrated mode.

## Source of truth to align with

From `baoyu-translate`:

- `SKILL.md` workflow: preferences/glossary -> analysis -> prompt -> translation/review
- `references/subagent-prompt-template.md`: `02-prompt.md` must be shared context, rich and complete
- `references/refined-workflow.md`: analysis dimensions and downstream usage

We will align structure and intent, but not require subagents. We will use parallel Gemini CLI calls where needed.

## Scope

### In scope

- Build a real analysis-to-prompt pipeline in BookWeaver orchestrated mode.
- Support `prompt-only` execution to generate `01-analysis.md` and `02-prompt.md` without translation.
- Default model strategy: Flash for analysis, prompt assembly, and translation.
- Keep optional model override hooks for future experimentation.

### Out of scope (first iteration)

- Full refined chain (`04-critique.md` / `05-revision.md`) automation.
- New external dependency for agent orchestration.
- Replacing existing fast mode behavior.

## Proposed architecture

### 1) Orchestrated phases

Add explicit orchestrated phases:

- `prompt-only`: generate `01-analysis.md`, `02-prompt.md`, stop
- `translate`: generate prompts, then translate pages

Both phases share the same prompt assembly logic.

### 2) Prompt assembly pipeline

For orchestrated mode:

1. Load runtime preferences:
   - output language
   - audience/style (default from config, override via CLI later)
2. Merge terminology inputs:
   - built-in glossary (existing assets)
   - project/user glossary sources (when present)
   - extracted terms from source pages
3. Build `01-analysis.md` with sections aligned to baoyu structure:
   - quick summary
   - core content
   - background context (lightweight first iteration)
   - terminology
   - tone & style
   - comprehension challenges
   - figurative language / structural challenges
4. Build `02-prompt.md` by composing:
   - target audience
   - style block
   - content background from analysis
   - merged glossary
   - comprehension challenge guidance
   - translation principles

### 3) Translation execution (non-subagent)

- Use shared `02-prompt.md` for all pages.
- Execute page translation with Flash.
- Support controlled parallelism (batch/page-level parallel command runs), with per-page isolation:
  - failure on one page does not silently discard others
  - final status reports failed pages explicitly

## Data contract and artifacts

Under `<temp_dir>/orchestration/`:

- `01-analysis.md`
- `02-prompt.md`
- `06-polish.md` (optional in first iteration; keep for compatibility if needed)
- `metrics.json` with:
  - mode/phase
  - models used
  - prompt length
  - page counts
  - failed page list (if any)

Page outputs remain `output_pageXXXX.md`.

## CLI and config changes

### CLI

- Keep `--workflow-mode orchestrated`.
- Add `--orchestrated-phase prompt-only|translate` (default `translate`).

### Config defaults

Add an `orchestrated` config section (with sane defaults):

- `analysis_model: gemini-2.5-flash`
- `prompt_model: gemini-2.5-flash`
- `translation_model: gemini-2.5-flash`
- `max_retries_per_page`
- `max_parallel_pages`

## Error handling policy

- No global all-or-nothing crash due to a single transient page error.
- Per-page retry with explicit retry budget.
- Emit clear summary:
  - translated count
  - failed count
  - failed page names
- `prompt-only` must fail fast if analysis/prompt generation fails.

## Testing strategy

### Unit tests

- analysis builder produces required sections
- prompt assembler includes required context blocks
- glossary merge precedence and deterministic ordering
- phase switch behavior (`prompt-only` vs `translate`)

### Integration tests

- orchestrated `prompt-only` generates artifacts and no `output_page*.md`
- orchestrated `translate` uses generated prompt and writes outputs
- transient failures retry per page and produce deterministic failure reports

### Regression checks

- existing fast mode tests unchanged
- full quality gates remain green (`ruff`, `pytest`, `bash -n`)

## Acceptance criteria

1. Generated `02-prompt.md` is analysis-driven and materially richer than static template.
2. `prompt-only` mode works and is inspectable for workflow validation.
3. Translation mode uses the generated prompt and reports per-page outcomes.
4. Default behavior uses Flash end-to-end.
5. Existing fast mode remains stable.
