---
specId: SPEC-028
title: Cross-Vendor Term Panel and Tiered Glossary
status: Approved by the owner (2026-11-09); amended 2026-11-10 (named panels, panel as its own step, availability, Deep Scan)
implementationStatus: Phase 1 implemented (PR 94) and adopted after live acceptance (2026-11-10); Phase 2a (`bookweaver terms`, PR 97) accepted on two books (2026-11-10, `docs/plans/2026-11-10-term-panel-acceptance.md`); Phases 2b-5 not started
priority: P1 - Translation Quality
creationDate: 2026-11-09
lastUpdateDate: 2026-11-10
owner: User (AI-Assisted)
relatedSpecs: [SPEC-010, SPEC-015, SPEC-024, SPEC-025]
tags:
  - glossary
  - term-extraction
  - llm-judge
  - subscription-cli
  - paid-consent
---

# SPEC-028: Cross-Vendor Term Panel and Tiered Glossary

## 1. Problem

Today one model extracts the terms, and every term enters the translation prompt as a strict rule ("必须严格遵守", `ai/core/glossary.py`). One extraction then fixes the terms for the whole book.

- One draw decides the book. Two Flash extractions of the same index shared 39 of 50 terms (issue 83).
- Each vendor has its own bias. Five models extracted about 50 terms each from the same index; only 10 terms were in all five lists.
- A weak translation is enforced everywhere. A majority vote enforced 一律化 for Uniformity, and the passage read worse.
- The owner does not judge English terms. A design that sends disputes to a person does not work for this owner.

Goal: several models from different vendors propose and judge the terms. A program combines the votes into a glossary with two tiers. The translator (default Gemini Flash) receives only that glossary.

## 2. Evidence (Political Thinking, 2026-11-09)

All runs used the trimmed EPUB of chapters 1 and 2 with the full book's index and table of contents, low effort, one run each, subscription CLIs only. Details and raw files: `docs/plans/2026-11-09-translation-evaluation-method.md`.

- **Vendors differ; models of one vendor do not.** Sonnet 5.5 and Opus 5.5 shared 37 of 50 terms. Opus shared 22 to 33 with each GPT or Gemini list. The five lists gave 107 candidates.
- **Judges show bias, and the measure depends on the unit.** Keep rate on a judge's own list against the other lists: Gemini Flash 100% vs 82%, Opus 98% vs 79%, Luna kept everything, Sol 86% vs 91% and 92% vs 88% in two rounds. Counted per vendor instead (candidates only the judge's vendor nominated), Opus kept 83% vs 88% and Sol 80% vs 94%: neither favored its own vendor. Per-vendor samples are small (12 and 35 candidates).
- **Panel composition decides close cases.** Sol chose 整齐划一 for Uniformity in all three of its runs. The first round's 一律化 came from a Gemini and Luna majority. With Opus as the second judge, the result became 整齐划一. Opus never ran without sentences, so the sentences' share in Opus's vote is unknown.
- **Book sentences help judges a little.** With up to three body sentences per term, Sol changed 14 of 107 translations; between two runs without sentences it changed 7 of 95. Some changes were clear gains (private ownership 私人所有权 → 私人所有制, from a passage about economic systems).
- **A preferred tier did no harm in chapters 1 and 2, and showed no benefit.** Flash translated the chapters twice with the same 91 terms: all strict, or 59 strict plus 32 as suggestions. Strict terms were used 38 of 38 times in both. Suggested terms were used 51 of 52 and 49 of 52 times; the two changes used the listed alternative. Only 9 suggested terms occur in these chapters.
- **Register dropped, cause unknown.** Both arms scored lower on the literary-word measure (5.53 and 5.98 per 1,000 characters) than both earlier Flash runs on the same chapters (6.13 each, with 50 and 78 terms). Run-to-run variation has not been measured, and the 91-term glossary is the largest so far. A large glossary may cost the style the translator was chosen for.
- **The vote rules replay.** Rules §3.4 applied offline to the second-round data (vendors: Google nominator; OpenAI and Anthropic as nominators and judges) gave 59 `fixed`, 34 `preferred` and 14 dropped. The dropped terms were single-vendor generic words (Power, Freedom), entries that judges called duplicates, and index-only terms. Every two-judge disagreement went to the tie-break, so the tie-break decides much of a two-judge panel; under rule 5 that is Sol (§5).

## 3. Decisions

### 3.1 Roles

| Role | Who | Output |
|---|---|---|
| Nominator | One or more presets | Candidate terms with one proposed translation each, from the existing extraction prompt |
| Judge | Zero or more presets | For each candidate: keep, translation, enforce (`fixed` or `preferred`), `duplicate_of`, confidence, note |
| Aggregator | Program, no model | Glossary with tiers, and a panel report |
| Translator | The run's preset | Translation with the glossary |

- The translator role takes one preset, as today. The term role takes one **named Term Panel**, or none.
- A Term Panel names its nominators and judges: each a list of presets from `ai/model_profiles.py` (SPEC-025 §3.8). A preset may serve in both lists. List order is significant: it is the last tie-break.
- Users choose a panel by name. No surface offers a free combination of presets (amendment 2026-11-10; the owner's rule that a profile is a named intent, not a model).
- With no panel configured, extraction and the prompt stay exactly as today. Existing books and checkpoints are unaffected.
- Nomination reads the index and table of contents (SPEC-015 Tier 1). SPEC-015's source ladder is unchanged; this spec decides who extracts and how results combine. One departure from the SPEC-015 resolution contract: there, `--glossary` wins over extraction flags with a warning; `--term-panel` with `--glossary` fails instead (§3.10), because a panel spends calls. Running `bookweaver terms` and then translating with `--glossary` is the normal route and is not a conflict.

### 3.2 Vendor, not model count

- Each preset carries a vendor: `google`, `openai` or `anthropic`. The registry gains this field for subscription presets and metered presets alike (`anthropic-pro` is `anthropic`). A future runtime that serves another vendor's models, such as Copilot, adds a quota pool, not a vote.
- One vendor casts one vote per role. Two presets from one vendor in the same role are rejected before any call, because their judgments correlate (Sonnet and Opus: 37 of 50 shared terms).
- "Own" in every rule below means the judge's vendor, not the judge's preset. A term only Sonnet nominated is Opus's own term.

### 3.3 Candidates and sentences

- Candidates are the union of all nominations. Never an intersection: a term only one vendor found can still be central.
- Key: the English term in lower case, hyphens as spaces, punctuation removed, and a leading "the", "a" or "an" removed. Entries that still differ but mean the same (Ortega y Gasset and Ortega y Gasset, Jose) are left to judges through `duplicate_of`.
- Each candidate lists every proposal with its nominating vendor. Judges see vendors as anonymous letters; the letter order is fixed per run and recorded in the report.
- Each candidate carries up to three body sentences that contain the term:
  - Excluded documents: the index document as found by the existing index detection in `ai/glossary_extractor.py`, the navigation document, and title pages.
  - Match: the whole phrase, case-insensitive, words joined by spaces or hyphens, optional plural ending. If that finds nothing, every content word of four or more letters (as a stem) must occur in one sentence.
  - Order: different documents first, then book order. A sentence over 400 characters is clipped around the match.
  - A candidate with no match carries an empty list, and the judge prompt says what that means.
  - In the experiment, the phrase match found 91 of 107 terms and the stem fallback raised it to 104. The selection rules are versioned in the cache identity.

### 3.4 Vote rules

A nomination is not a vote. Only judges vote.

1. **Duplicates.** A judge may set `duplicate_of` to another candidate's id. When at least half of the judges name the same target, the candidate merges into it: its proposals join the target, and it gets no entry of its own. The report lists merges.
2. **Own-term rule.** A judge's `keep: true` does not count for a candidate that only the judge's own vendor nominated. Its `keep: false` and its translation still count. When another vendor also nominated the term, the vote counts.
3. **Keep.** A candidate is dropped only when its counted drop votes outnumber its counted keep votes. A tie keeps it. With no judge, every candidate stays.
4. **Translation.** Sources are every judge that kept the candidate, plus each nominating vendor that is not a judge, with that vendor's proposal. The most common translation wins. Ties:
   - With judges: the translation of the tie-break judge (below).
   - With no judge: the proposal of the first nominator in the configured order.
   - If no judge kept the candidate but it stayed by rule 3, all judges' translations count as sources.
5. **Tie-break judge.** For each judge: self-preference = keep rate on candidates only its vendor nominated, minus keep rate on all others; a negative value counts as zero. The tie-break judge has the smallest self-preference. A judge with fewer than 10 own-vendor candidates is unmeasured and ranks after measured judges. Remaining ties follow the configured order. No vendor is named in advance.
6. **Tier.**
   - `fixed` only when all of these hold: at least two sources gave the chosen translation; no judge that kept the term gave another translation; and every judge that kept it said `fixed`.
   - Otherwise `preferred`, with up to two alternatives from the other translations, most common first.
7. **Size cap.** `--glossary-max-terms` (SPEC-015) caps the final glossary, not each nominator. Order for the cap: `fixed` before `preferred`, then more nominating vendors first, then `priority`, then the key.

Panel sizes:

| Nominators | Judges | Result |
|---|---|---|
| 1 | 0 | Today's behavior: one extraction, every term strict, no tier field |
| 1 | 1, another vendor | A review: the judge can drop terms and correct translations; a term is `fixed` only when the judge agrees with the nominator |
| 2 or more | 0 | Union of nominations; a term two vendors translated alike is `fixed`, the rest `preferred` |
| 2 or more | 1 | The judge's drop vote decides alone. Terms only the judge's vendor nominated stay, because the judge's keep does not count and a lone drop is not a tie |
| 2 or more | 2 or more | Full vote as above |

No rule sends a term to a person. The owner may still edit the glossary file before translation, as today.

### 3.5 Tiered glossary and prompt

- A term gains an optional `tier` field: `fixed` or `preferred`. `alternatives` already exists in the extraction schema and now reaches the prompt for `preferred` terms only.
- `tier` controls strictness. `priority` (`critical`, `high`, `medium`) keeps its current meaning: filtering with `--glossary-min-priority`, ordering, and the size cap. The two are separate axes.
- The prompt has two blocks:
  - `fixed` terms keep today's heading and wording.
  - `preferred` terms get a new block: use this translation normally; when a sentence needs it, use a more fitting one without changing the meaning. Alternatives follow each term.
- A glossary in which no term has `tier` renders byte-identically to today. The prompt hash of every existing book stays valid. A prompt-hash test in `tests/unit/test_prompt_preparation.py` pins this through prompt preparation, with a hash taken from the code before tiers.
- `term-consistency.json` grades the tiers separately. Only `fixed` drift is reported as a problem.

### 3.6 Judge bias report

- For each judge, the report gives the per-vendor self-preference of §3.4 rule 5, its sample size, and the keep rate on its own preset's list.
- The aggregator uses it only for the tie-break. It never drops a judge automatically. The owner reads the report.

### 3.7 Cache, reuse and saved replies

- Location: `<book folder>/.bookweaver_glossaries/panel/<sha256>/`, holding `glossary.json`, `term-panel-report.json` and `replies/`. For `bookweaver terms` the book folder is the `--output-dir` it is given, default the EPUB's folder. For a local API upload it is the library folder `~/Documents/BookWeaver/<book name>/`, which every output folder of that book shares. This closes issue 86 for panel runs.
- Identity: source signature, mode, the glossary cap and the per-nominator request (§3.4 rule 7), nominator and judge presets in order with their model IDs (a preset re-pointed to another model misses the cache), `judge_prompt_max_chars`, the extraction prompt version, the sentence-selection version and the rule version. It is separate from the single-extraction key `glossary_cache_path`, which is unchanged.
- Each member's raw reply is saved next to the cache under the same identity plus the member and chunk. A rerun after a failure reuses saved replies and calls only the missing members.
- The cached glossary feeds the prompt hash, as today. A changed panel gives a new identity and a new glossary; it never rewrites a saved one.

### 3.8 Paid members

- A panel may include metered presets (SPEC-024), as nominator or as judge.
- The panel runs as its own step (§3.10), so its consent is its own: `bookweaver terms --allow-paid-api` covers the paid members it lists by name, and the translation run keeps today's gate unchanged. Only the inline API path (§3.10) runs both steps in one child; it gets separate consent for the panel. Either way this touches the paid-call gate and needs the deep review.
- No automatic fallback in either direction. The program never adds or substitutes a paid member.

### 3.9 Failure and scale

- Each nominator makes one call, as today.
- A judge gets all candidates in one call when the prompt fits the runtime's limit. Otherwise candidates go out in chunks; one chunk always holds all candidates that share a head word, so that `duplicate_of` can see them together. The experiment used one call of 107 candidates (about 107,000 characters); chunking is untested.
- A reply that is not a JSON array, or has a wrong shape, fails that judge's chunk. A missing candidate id counts as an abstention for that candidate and is reported.
- Any member failure, including quota and authentication, stops the run before translation. The report names the member and the error. The panel is never shrunk silently; the owner reruns, and saved replies are reused (§3.7).
- The run prints the planned number of calls per member before the first call.

### 3.10 Interface

**The panel is its own step, and its only output is a tiered glossary file.** Phase 1 made that file a complete interface: `--glossary` already consumes it. So the translation path does not change.

- **Terms command:** `bookweaver terms BOOK.epub --panel NAME [--output-dir DIR] [--glossary-mode deep-scan] [--glossary-max-terms N] [--allow-paid-api]`. It writes the glossary and `term-panel-report.json` into the cache folder (§3.7) and prints the glossary path. No translation.
- **Translation, two ways:**
  - `bookweaver BOOK.epub --glossary PATH --preset NAME` uses a glossary from `bookweaver terms` like any other. The translation path is unchanged.
  - `bookweaver BOOK.epub --term-panel NAME --preset NAME` runs the same panel resolver in the same process before translating, then uses its glossary. This is one command, so the local API's run record and child lookup (`launch`, `_locate`) stay as they are.
- **Panels are named in configuration**, validated by `ai/config_schema.json`:

```json
"terminology_panels": {
  "three-vendor": {
    "nominators": ["agy-flash-low", "codex-gpt-6.1-sol-low", "claude-opus-5-5-low"],
    "judges": ["codex-gpt-6.1-sol-low", "claude-opus-5-5-low"]
  }
}
```

  - The key is the panel name users see. A panel is configuration, not evidence: it has no status field. Evidence about a panel lives in `docs/plans/`, as for presets. No run uses a panel unless asked; there is no default panel.
  - `config/config.json.example` shows this panel. The owner adds panels to their own configuration by hand; nothing rewrites it. An unknown panel name fails and prints the example.
- **Local API upload (Phase 4):** one optional field, `term_panel`, a dropdown of panel names built like `PresetName`, default none.
  - With a panel, the child is the translate command with `--term-panel NAME`, inside the existing run record and the one-run rule.
  - The upload stops sending `extraction_model` when a panel is chosen; the two conflict.
  - Output folder: `<book>/panel-<name>-<id>/<preset>/`, where `<id>` is the first eight characters of the panel's cache identity (§3.7). Editing a panel's members gives a new folder, so a run never resumes a checkpoint made with another glossary. The upload still has no `--force-resume`.
  - Paid panel members are not offered on the upload in the first version.
- **Conflicts on `--term-panel`, before any call:** with `--glossary`, `--extraction-model` or `--extract-glossary`. A panel replaces the extraction that `terminology_extraction.enabled` turns on; that is not a conflict. `--term-panel` keeps the panel cache beside the EPUB, which is where `bookweaver terms` writes it by default, and computes the term limits with the same function, so a glossary from `bookweaver terms` is reused without a call. **On `--term-panel` and `bookweaver terms` alike:** an unknown panel; a panel that names an unknown, disabled or unavailable preset (§3.12); two presets of one vendor in one list; a single nominator whose vendor is the only judge vendor (every keep vote would be void).

### 3.11 Persistent structure changed

These are Structure paths in `docs/agents/impact-radius.md`. This list is the design for approval:

| Structure | Change |
|---|---|
| Glossary file format (`ai/glossary_extractor.py`, `ai/core/glossary.py`) | Optional `tier` per term; `alternatives` read by the prompt for `preferred` terms. Files without `tier` stay valid and render as today |
| Glossary block (`GlossaryManager.format_block`) | Second block for `preferred` terms; unchanged output when no term has `tier` |
| Glossary cache | A new panel folder and identity (§3.7) beside `glossary_cache_path`, whose identity and files are unchanged |
| New files | `term-panel-report.json` and saved member replies under `.bookweaver_glossaries/panel/` |
| Runtime configuration schema | Optional `terminology_panels` (named panels, §3.10) and `runtimes.disabled` (§3.12); `config/config.json.example` gains one example panel. The validator in `ai/runtime_config.py` gains `array`, `items`, `minItems`, `minLength` and `required`, which no earlier key used |
| Model registry (`ai/model_profiles.py`) | `vendor` on every preset, subscription and metered; no `model_id` changes |
| Deep Scan prompt (`ai/glossary_extractor.py`, Phase 5) | Real title and table of contents; bumps `extractor_version` for Deep Scan caches only |
| Term report (`term-consistency.json`) | Per-tier grading; reports without tiers keep their current shape |
| Invocation audit (`.bookweaver_runs/<run_id>.json`, Phase 2b) | New field `term_panel`: `null`, or the panel `name`, its cache `identity`, `reused`, and `members` (each `role`, `preset`, `model`). It is set before any member is created, so a refused or failing member still appears; like every audit field, it is written when the run ends, including on an exception, but not when the process is killed. `extraction_model` keeps its meaning and is `null` on a panel run. Votes and failures stay in `term-panel-report.json`. Owner decision, 2026-11-10 |

No checkpoint schema change. A tiered glossary changes `system_prompt_hash` only for books that use it.

### 3.12 Availability: code records evidence, configuration records subscriptions

- Presets stay in code (`ai/model_profiles.py`): model ID, probe evidence, status. They change with evidence, in a reviewed change.
- Which subscriptions the owner has is configuration: an optional `runtimes.disabled` list (for example `["codex"]`). A disabled runtime's presets leave `GET /presets`, the upload dropdown and `bookweaver presets` (which marks them `disabled`), and any run that names one fails before a call.
- Cancelling a subscription is therefore a configuration edit: disable the runtime and remove it from panels. No code change.
- A panel that names a disabled or logged-out member stops before any call and names the member. The program never shrinks a panel silently.
- Readiness before any model call means login, version and, where the runtime lists its models, the roster. Claude Code has no model list, so a Claude model the account cannot use is found by its compatibility probe on first use; by then earlier nominators may have answered. Their replies are saved, so the rerun repeats no call.
- Availability is checked only when a member must be called. A book whose panel glossary is already cached resumes even after a member's subscription ended.
- If the default preset's runtime is disabled, it leaves `GET /presets` like any other disabled preset, and the upload requires an explicit preset; the default never changes silently.
- Delivered in Phase 2b: `bookweaver presets` (table and `--json`) shows `disabled` as the status of such presets; `GET /presets` and the upload's preset dropdown leave them out, read once when `serve` starts; a disabled default leaves the upload without a default, so it requires an explicit preset; before starting a child, `POST /runs/upload` refuses a disabled preset with 422 (it is not among the dropdown's choices) and `POST /runs` with 400; a translation model or panel member on a disabled runtime fails before any call.
- The local API may show login status from the existing login checks (`codex login status`, `claude auth status`), which spend no quota. It only reports; it never edits a panel.

### 3.13 Deep Scan with a panel

Deep Scan sends the whole book in one request (`ai/glossary_extractor.py`; well over half a million characters for *Political Thinking*). It is the only route for books without an index, which are common among older humanities books.

- **One nominator only.** Several whole-book requests multiply quota, and no runtime has evidence at this input length. A Deep Scan run requires a panel with exactly one nominator and fails before any call otherwise. The owner names such panels separately, for example `deep-scan-gemini`.
- **Judges are unchanged.** They read candidates, body sentences (found locally, no model) and the table of contents, not the book. So a Deep Scan book still gets a cheap cross-vendor vote.
- The Deep Scan prompt gains the book's real title and the table of contents. Today it sends the title `Unknown`.
- Deep Scan has no live evidence on a subscription CLI (issue 71). Phase 5 needs that evidence first.
- Parked idea (owner, 2026-11-10): the Deep Scan model also returns the sentences it based each term on, and those feed the judges. Not in scope; recorded so it is not lost.

### 3.14 Three reading depths

The owner's rule: hide no setting, but tier the views, and build every view from one resolved plan.

- **Ordinary:** choose a preset and, optionally, a panel name.
- **Confirm:** before the first call, `bookweaver terms` prints the resolved plan: each member's preset, runtime (quota pool), vendor and planned calls, and whether any call is paid. The upload returns the same plan in its response.
- **Inspect:** `term-panel-report.json` (votes, merges, tiers, each judge's self-preference, its sample and its keep rate on its vendor's own list, failures) and `term-consistency.json`.
- A panel may set `judge_prompt_max_chars` (default 200,000); a judge prompt longer than that is split into chunks (§3.9).

The plan and the report come from the same resolver that runs the panel; no surface keeps a second copy of the rules.

## 4. Out of scope

- Several nominators in Deep Scan (§3.13).
- Free combinations of presets on any surface. New combinations are new named panels.
- A Copilot runtime. It would add a quota pool, not a vote; add it only when quota requires.
- A human dispute step. The owner does not judge English terms.
- Web search during judging.
- Judging or auditing the translation itself: SPEC-025 §3.7 and its evaluation spec.
- Running extraction as its own step in the local API: issue 71.

## 5. Open items

- [x] Owner confirmed on 2026-11-09: one vote per vendor (§3.2), not one per preset.
- [x] Owner confirmed on 2026-11-09: the tie-break of §3.4 rule 5. With two judges it decides every disagreement. Correction, 2026-11-10: the replay first ranked judges by the absolute gap and named Opus. Under rule 5 as written, a negative self-preference counts as zero, both judges score zero, and configured order decides: Sol, the first judge of `three-vendor`. The counts (59 fixed, 34 preferred, 14 dropped) are unchanged; tied terms such as Cosmic morale (面对宇宙的精神底气) and Cosmopolis (宇宙城邦) follow Sol. An offline check of `ai/core/term_panel.py` against the replay data in the owner's trial folder matched it term for term (2026-11-10); that data is not in the repository, so no test pins it.
- [x] Run-to-run register variation, measured on ch007 (2026-11-10): two strict runs differed by 0.54 per 1,000 characters; the 91-term glossary did not lower register there.
- [x] Owner feedback, 2026-11-10: do not normalize terms fully; adapting a word to the sentence is welcome. Decision: no new field. The judge prompt defines `enforce: fixed` narrowly: an author's coined concept, a person's name, a title, or an established doctrine or school. Everything else is `preferred`.
- [ ] Gemini Pro (`agy-pro-low`) has not judged, and the owner cannot use it at present. A Google vote is Gemini Flash until then; Flash showed self-preference per preset, which the own-term rule offsets.
- [ ] Confirm the prompt limit per runtime before relying on one-call judging.
- [ ] `duplicate_of` is new; no judge has produced it yet.
- [ ] Deep Scan input length per runtime: which runtimes accept a whole book in one request.

## 6. Phases

1. **Tiered glossary (done; adopted 2026-11-10, `docs/plans/2026-11-10-tiered-glossary-acceptance.md`).** `tier` field, two prompt blocks, byte-identical rendering for old glossaries, tiered term report. Offline tests through prompt preparation and the term report.
   - Live acceptance: one chapter with several `preferred` terms (where Cosmic morale or Socratic civility occur; chapters 1 and 2 hold only nine), translated strict and tiered with the same glossary. Also measure register for both.
   - Gate, fixed before the run: adopt tiers when `fixed` drift is zero in the tiered version, register does not fall, and the owner does not prefer the strict version. Otherwise keep one strict block and record why. Closes issue 82 either way.
2. **Terms command and `--term-panel` on the index path, subscription presets only.** Delivered in two PRs: 2a, `bookweaver terms` with vendors, named panels, the readiness check (`ITranslationProvider.check_ready`, login, version and roster without a model call) and everything below except availability; 2b, `--term-panel` on the translate command and `runtimes.disabled`. Vendor field, named panels in configuration, `runtimes.disabled`, candidates with sentences, judges, aggregator, resolved plan, report, cache, saved replies. Offline tests: the vote rules through `ai/core/term_panel.py` (panel sizes, own-term rule, duplicates, both tie-breaks, the cap, the report); the runner through `run_term_panel` with an in-process fake factory (refusals, readiness, failure stop and reuse, cache reuse and identity, sentences, nav and index exclusion); `check_ready` through a fake `codex` executable. `scripts/` in the owner's trial folder holds the reference pipeline (`replay.py` for the vote rules).
   - Phase 2a accepted 2026-11-10 (`docs/plans/2026-11-10-term-panel-acceptance.md`); the owner kept the term limit at 100.
   - Phase 2b implemented 2026-11-10 (issue 100): `--term-panel` through `plan_glossary` in `ai/term_extraction.py`, which plans the panel with `plan_panel` (no call) before `run_panel` executes it; `runtimes.disabled`; the audit field in §3.11. Offline tests in `tests/unit/test_term_panel_translation.py`. Checkpoints written by main (no glossary, extracted, supplied, and a panel glossary passed with `--glossary`) resumed on the branch with zero calls and byte-identical checkpoints, the last one with `--term-panel`. No live run yet.
   - Live acceptance: the owner adds the `three-vendor` panel to their configuration; then *A Philosophy of Software Design* (index 4,846 characters, no panel data yet) and *Political Thinking*, each with that panel, then translated with `agy-flash-low` into new folders, never resuming old checkpoints. Compare *Political Thinking* with the replay in §2.
3. **Paid members.** Consent on `bookweaver terms`, through the deep review. Offline tests only, unless the owner authorizes a paid call.
4. **Local API.** The `term_panel` dropdown, the panel output folder, login status display.
5. **Deep Scan with a panel.** After issue 71 has live evidence. One nominator, title and table of contents in the prompt.

## 7. Verification

- `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`, `uv run tach check`, `uv run python scripts/check_doc_links.py`.
- Test public behavior: the rendered prompt, the glossary file, the report, and which calls a fake executable received.
- Live runs are recorded in `docs/plans/`, separately from mocked tests.

## 8. Related

- SPEC-010 introduced the strict term block. §3.5 keeps it for `fixed` terms and adds the `preferred` block.
- SPEC-015 defines where candidates come from and the `--glossary-max-terms` cap. §3.1 records the one departure.
- SPEC-024 defines paid consent. §3.8 extends it to panel roles.
- SPEC-025 §3.7 covers judging translations; this spec covers judging terms.
- Issues 71, 82, 83 and 86.
