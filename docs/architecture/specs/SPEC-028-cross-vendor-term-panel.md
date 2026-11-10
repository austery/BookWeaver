---
specId: SPEC-028
title: Cross-Vendor Term Panel and Tiered Glossary
status: Draft for owner review (2026-11-09)
implementationStatus: Not started
priority: P1 - Translation Quality
creationDate: 2026-11-09
lastUpdateDate: 2026-11-09
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
- Each vendor has its own bias. Five models extracted 50 terms each from the same index; only 10 terms were in all five lists.
- A wrong or weak rendering is enforced everywhere. A majority vote enforced 一律化 for Uniformity, and the passage read worse.
- The owner does not judge English terms. A design that sends disputes to a person does not work for this owner.

Goal: several models from different vendors propose and judge the terms. A program combines the votes into a glossary with two tiers. The translator (default Gemini Flash) receives only that glossary.

## 2. Evidence (Political Thinking, 2026-11-09)

All runs used the trimmed EPUB of chapters 1 and 2 with the full book's index and table of contents, low effort, one run each, subscription CLIs only. Details and raw files: `docs/plans/2026-11-09-translation-evaluation-method.md`.

- **Vendors differ; models of one vendor do not.** Sonnet 5.5 and Opus 5.5 shared 37 of 50 terms. Opus shared 22 to 33 with each GPT or Gemini list. The five lists gave 107 candidates.
- **Judges have measurable bias.** Keep rate on own proposals against others' proposals: Gemini Flash 100% vs 82%, Opus 98% vs 79%, Luna kept everything, Sol 92% vs 88% and 86% vs 91% in two rounds.
- **Panel composition decides close cases.** Sol chose 整齐划一 for Uniformity in all three of its runs. The earlier 一律化 came from a Gemini and Luna majority. With Opus as the second judge, the result became 整齐划一.
- **Book sentences help judges a little.** With up to three body sentences per term, Sol changed 14 of 107 renderings; between two runs without sentences it changed 7 of 95. Some changes were clear gains (private ownership 私人所有权 → 私人所有制, from a passage about economic systems).
- **A preferred tier did no harm in chapters 1 and 2.** Flash translated the chapters twice with the same 91 terms: all strict, or 59 strict plus 32 as suggestions. Strict terms were used 38 of 38 times in both. Suggested terms were used 51 of 52 and 49 of 52 times; the two changes used the listed alternative. Only 9 suggested terms occur in these chapters, so the benefit is unproven.

## 3. Decisions

### 3.1 Roles

| Role | Who | Output |
|---|---|---|
| Nominator | One or more presets | Candidate terms with one proposed translation each, from the existing extraction prompt |
| Judge | Zero or more presets | For each candidate: keep, translation, enforce (`fixed` or `preferred`), confidence, note |
| Aggregator | Program, no model | Glossary with tiers, and a panel report |
| Translator | The run's preset | Translation with the glossary |

- A role is a list of named presets from `ai/model_profiles.py` (SPEC-025 §3.8). A preset may serve in both roles.
- With no panel configured, extraction and the prompt stay exactly as today. Existing books and checkpoints are unaffected.
- Nomination reads the index and table of contents (SPEC-015 Tier 1). The extraction source ladder in SPEC-015 is unchanged; this spec decides who extracts and how results combine.

### 3.2 Vendor, not model count

- Each preset carries a vendor: `google`, `openai` or `anthropic`. The registry gains this field.
- One vendor casts one vote per role. Two presets from one vendor in the same role are rejected before any call, because their judgments correlate (Sonnet and Opus: 37 of 50 shared terms).
- The panel report always names the vendors that took part.

### 3.3 Candidates

- Candidates are the union of all nominations, keyed by the normalized English term: lower case, hyphens as spaces, punctuation removed. Never an intersection: a term only one vendor found can still be central.
- Each candidate lists every proposal with its nominating vendor. Judges see vendors as anonymous letters A, B, C; the letter order is fixed per run and recorded in the report.
- Each candidate carries up to three body sentences that contain the term. The index, navigation and title documents are excluded. The selection is deterministic: different documents first, then book order; a sentence over 400 characters is clipped around the match. A candidate with no match carries an empty list, and the judge prompt says what that means.

### 3.4 Vote rules

A nomination is not a vote. Only judges vote.

1. **Own-term rule.** A judge's `keep: true` does not count for a candidate that only the judge's own vendor nominated. Its `keep: false` and its translation still count. When another vendor also nominated the term, the vote counts.
2. **Keep.** With no judge, every candidate stays. Otherwise a candidate stays when its counted keep votes outnumber its drop votes. A candidate with no counted votes stays only if two or more vendors nominated it.
3. **Translation.** Count every judge that kept the candidate, and add each nominating vendor's proposal as one source when that vendor is not also a judge. The most common translation wins. On a tie, take the translation of the judge with the smallest measured bias in this run (§3.6). Never a fixed vendor.
4. **Tier.**
   - `fixed` only when all of these hold: at least two vendors gave the chosen translation, no judge that kept the term gave another translation, and every judge that kept it said `fixed`.
   - Otherwise `preferred`, with up to two alternatives taken from the other translations, most common first.
5. **Panel sizes.**

| Nominators | Judges | Result |
|---|---|---|
| 1 | 0 | Today's behavior: one extraction, every term strict |
| 1 | 1, another vendor | A review: the judge can drop terms and correct translations; a term is `fixed` only when the judge agrees with the nominator |
| 2 or more | 0 | Union of nominations; terms that two vendors translated alike are `fixed`, the rest `preferred` |
| 2 or more | 2 or more | Full vote as above |

No rule sends a term to a person. The owner may still edit the glossary file before translation, as today.

### 3.5 Tiered glossary and prompt

- A term gains an optional `tier` field: `fixed` or `preferred`. `alternatives` already exists in the extraction schema and now reaches the prompt for `preferred` terms only.
- `tier` controls strictness. `priority` (`critical`, `high`, `medium`) keeps its current meaning: filtering with `--glossary-min-priority` and ordering. The two are separate axes.
- The prompt has two blocks:
  - `fixed` terms keep today's heading and wording.
  - `preferred` terms get a new block: use this translation normally; when a sentence needs it, use a more fitting one without changing the meaning. Alternatives follow each term.
- A glossary in which no term has `tier` renders byte-identically to today. The prompt hash of every existing book stays valid. A test pins this.
- `term-consistency.json` grades the tiers separately. Only `fixed` drift is reported as a problem.

### 3.6 Judge bias

- For each judge, the report gives the keep rate on candidates only its vendor nominated, and on all others.
- The aggregator uses this only for the tie-break in §3.4. It never drops a judge automatically. The owner reads the report.

### 3.7 Cache and reuse

- The panel glossary is cached per book. The identity holds: source signature, mode, term limit, nominator presets, judge presets, sentence-selection version and rule version.
- Runs that compare translation models on one book reuse one panel glossary. This closes issue 86 for panel runs.
- The cached glossary feeds the prompt hash, as today. A changed panel gives a new identity and a new glossary; it never rewrites a saved one.

### 3.8 Paid members

- A panel may include metered presets (SPEC-024), as nominator or as judge.
- Consent is per run and lists every paid member by name. Today `--allow-paid-api` requires a metered translator and the factory refuses it for a CLI model. Consent must become per role, so that a CLI translator can run with a paid judge. This touches the paid-call gate and needs the deep review.
- No automatic fallback in either direction. A paid member is never added or substituted by the program.

### 3.9 Failure and scale

- Each nominator makes one call, as today.
- Judges receive candidates in chunks of at most 60, with sentences. Every chunk carries the same instructions, table of contents and index.
- A judge reply that is not a JSON array, or that has a wrong shape, fails that judge's chunk. A missing candidate id counts as an abstention for that candidate and is reported.
- Any member failure, including quota and authentication, stops the run before translation. The report names the member and the error. The panel is never shrunk silently; the owner reruns with fewer members.
- The run prints the planned number of calls per member before the first call.

### 3.10 Interface

- CLI: `--term-nominators PRESET[,PRESET...]` and `--term-judges PRESET[,PRESET...]`.
- Configuration: `terminology_panel.nominators` and `terminology_panel.judges`, validated by `ai/config_schema.json`.
- Local API upload: the same two lists, chosen from `GET /presets` (Phase 4).
- These conflict and fail before any call: a panel with `--glossary`; a panel with `--extraction-model`; a panel with `--glossary-mode deep-scan` (§4); two presets of one vendor in one role; judges whose only vendor is the sole nominator's vendor (the own-term rule would void every vote); an unknown or disabled preset.
- Outputs next to the glossary cache: the glossary and `term-panel-report.json` (candidates, proposals, votes, tiers, bias, failures, call counts).

## 4. Out of scope

- Several nominators in Deep Scan. A whole-book scan is the most expensive nomination and has no live evidence on a subscription CLI (issue 71). When added, Deep Scan keeps one nominator and may add judges, because judging reads only candidates and sentences.
- A human dispute step. The owner does not judge English terms.
- Web search during judging.
- Judging or auditing the translation itself: SPEC-025 §3.7 and its evaluation spec.
- Running extraction as its own step in the local API: issue 71.

## 5. Open items

- [ ] Owner: confirm one vote per vendor (§3.2), rather than one per preset.
- [ ] Measure Sol's bias over more books before treating any judge as unbiased.
- [ ] Phase 1 acceptance needs a chapter with several `preferred` terms (for example where Cosmic morale or Socratic civility occur). Chapters 1 and 2 hold only nine.
- [ ] Gemini Pro (`agy-pro-low`) has not judged, and the owner cannot use it at present. A Google vote is Gemini Flash until then; Flash showed self-preference, which the own-term rule offsets.
- [ ] Prompt size: the 107-candidate judge prompt was 107,000 characters in one call. Confirm the 60-term chunk on each runtime.

## 6. Phases

1. **Tiered glossary.** `tier` field, two prompt blocks, byte-identical rendering for old glossaries, tiered term report. Offline tests through prompt preparation and the term report. Live acceptance: one chapter with several `preferred` terms, translated strict and tiered; the owner reads both. Closes issue 82 if adopted.
2. **Panel on the index path, subscription presets only.** Vendor field, candidates with sentences, judges in chunks, aggregator, report, cache, CLI and configuration. Offline tests with fake executables: vote rules for each panel size, own-term rule, tie-break, failure stop, conflicts, cache identity. Live acceptance: *Political Thinking* with one Google, one OpenAI and one Anthropic member in each role, then chapters 1 and 2 translated with the result.
3. **Paid members.** Per-role consent, through the deep review. Offline tests only, unless the owner authorizes a paid call.
4. **Local API.** Panel lists on upload; shared glossary per book.

## 7. Verification

- `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`, `uv run tach check`, `uv run python scripts/check_doc_links.py`.
- Test public behavior: the rendered prompt, the glossary file, the report, and which calls a fake executable received.
- Live runs are recorded in `docs/plans/`, separately from mocked tests.

## 8. Related

- SPEC-010 introduced the strict term block. §3.5 keeps it for `fixed` terms and adds the `preferred` block.
- SPEC-015 defines where candidates come from. Unchanged.
- SPEC-024 defines paid consent. §3.8 extends it to panel roles.
- SPEC-025 §3.7 covers judging translations; this spec covers judging terms.
- Issues 71, 82, 83 and 86.
