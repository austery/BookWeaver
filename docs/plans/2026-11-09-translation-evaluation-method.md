# Translation evaluation method and first evidence (2026-11-09)

**Purpose:** record how BookWeaver evaluates models, terms and translations, and what the first comparison showed. This is the input for the evaluation spec that SPEC-025 §3.7 and Phase 4 call for. It is not that spec.

**Conclusion:** use several models for terms and review, but measure each judge before trusting it, and keep a human decision for disputed terms. Gemini 3.8 Flash stays the translator, because the owner prefers its style.

## Principles

1. **Style and fidelity are separate axes.** Report each one on its own. A sampled fidelity check favored the GPT models; the owner's reading favored Gemini's literary Chinese. Neither result cancels the other.
2. **The owner's reading is the human half of the evaluation** (SPEC-025 §3.7). An AI judge supports it and does not replace it.
3. **Change one variable at a time** (SPEC-025 §3.8). Hold the source, the segmenter and the glossary fixed when you compare translation models. Hold the translation model fixed when you compare glossaries.
4. **Merge candidate terms; do not intersect them.** An important term that only one model found is lost by an intersection. Filter the union instead.
5. **Hide the source of each candidate from the judges.** Label lists A, B, C.
6. **Measure each judge before you trust it.** Compare how often a judge keeps its own proposals with how often it keeps others'. A judge that keeps everything does not filter. Only a judge with no measured bias may break ties.
7. **A majority vote is not the truth.** Once a glossary is enforced, a weak majority rendering is enforced everywhere. The owner decides the short list of disputed terms.
8. **Prefer a judge from a vendor that did not translate.** This reduces self-preference.
9. **Audit, do not retranslate.** A second model checks only flagged segments (term inconsistency, sanity warnings, negation, numbers, causes) and reports errors. It does not translate the book again.
10. **Test on part of a book first.** Two chapters show most differences at about a quarter of the cost.
11. **Spend paid calls only with consent.** Subscription CLIs are the default judges. A paid API judge needs the existing per-run consent and is useful only when no independent vendor is on a subscription, or to break a tie.

## Workflow

| Step | Action | Owner |
|---|---|---|
| 1. Candidates | Book title, TOC, index and definition sentences as fixed inputs; two or three models extract terms; merge the union | Models |
| 2. Cross-review | Anonymized judges decide keep or drop and one best rendering per term, with the TOC and index as evidence | Measured judges, at least one from another vendor |
| 3. Decision | The owner decides the disputed terms; the rest follow the vote | Owner |
| 4. Translation | Translate with the final glossary | Gemini 3.8 Flash |
| 5. Audit | Another vendor checks flagged segments and reports errors | Judge model |
| 6. Calibration | On a shared sample, measure how often the AI judge agrees with the owner | Owner and judge |

Open parts:

- Term tiers (`fixed`, `contextual`, `preferred`): issue 82.
- Fixed candidates from the book's structure: issue 83.
- One glossary shared across compared models: issue 86.
- Claude Code as a judge runtime: SPEC-025 Phase 3, second half.

## Measures used

- **Alignment:** every compared segment exists in every version, matched by segment ID.
- **Omission check:** a segment over 200 characters whose translation is under 70% of the median length across versions.
- **Untranslated English:** four or more consecutive English words of four letters or more.
- **Literary register:** occurrences per 1,000 characters of 抑或、诸如、无异于、乃、亦、之所以、皆、故而、遂、然而、何以、此种、其、即便、实则、毋宁. Colloquial register: 还是说、这样、这种、我们、东西、的话、就是、所以、但是、也就是说. These lists are rough proxies, not validated measures.
- **Term use:** for each glossary term found in the source segments, the share of those segments whose translation contains the glossary rendering.
- **Judge bias:** keep rate on a judge's own proposals against keep rate on other lists' proposals.

## Evidence: *Political Thinking*, chapters 1 and 2

Source: Glenn Tinder, *Political Thinking: The Perennial Questions*. A trimmed EPUB kept the front matter, the introduction, chapters 1 and 2, and the index in the spine. Its index and TOC text match the full book exactly (21,460 and 3,096 characters), so term extraction saw the same input. Chapters 1 and 2 have 188 segments and about 98,000 source characters. All models ran at low effort, one run each. The owner authorized the subscription calls; no paid API was used.

### Translation models

| Version | Glossary | Chinese chars | Literary per 1,000 | Colloquial per 1,000 |
|---|---|---|---|---|
| Gemini 3.8 Flash (full-book retest) | Gemini Flash | 30,023 | 6.13 | 11.69 |
| `gpt-6-luna` | Luna | 28,530 | 4.00 | 12.09 |
| `gpt-6.1-terra` | Luna | 29,853 | 4.12 | 13.03 |
| `gpt-6.1-sol` | Sol | 30,099 | 4.12 | 12.16 |

- No version omitted a segment.
- In three sampled passages, Terra and Sol were the most faithful. Gemini mistranslated a musical metaphor (harmony as 交响乐, theme as 一首诗).
- The owner read the side-by-side file and chose Gemini: the GPT versions read like a translation draft.
- A generic style instruction (`-p`: 译文用中文学术出版物的书面语，句式符合中文习惯，避免翻译腔；不得增删原意) on chapter 1 left Terra at 4.22 and moved Sol from 4.51 to 5.27; Gemini was 6.32 on the same chapter. A stronger instruction with examples, or medium effort, is untested.

### Term extraction

Each model extracted 50 terms from the same index and TOC.

- Only 13 terms appeared in all three lists. Gemini had 19 terms of its own, Luna 15, Sol 20.
- Gemini favored named doctrines (Will to power, Two swords doctrine). Sol added names and titles but also generic words (Being, Power, Unity). Luna added near-duplicate pairs.
- The extraction model shapes the glossary more than the translation model does.

### Cross-review of the merged glossary

The union held 95 candidates. Each of the three models judged all of them once, with the lists anonymized.

| Judge | Kept | Own proposals kept | Others' proposals kept |
|---|---|---|---|
| Gemini 3.8 Flash | 87 | 50 of 50 | 37 of 45 (82%) |
| `gpt-6-luna` | 95 | all | all |
| `gpt-6.1-sol` | 84 | 43 of 50 (86%) | 41 of 45 (91%) |

- Luna did not filter, and Gemini showed self-preference. Keep or drop therefore used Gemini and Sol: both kept 78, one kept 15, neither kept 2 (both duplicates).
- The three judges agreed on 81 of 95 renderings, two agreed on 12, and all differed on 2.
- Agreement fixed real errors: Transcendentalism 先验论 → 超验主义, Humane Uncertainty 人文 → 人道的不确定性 (Luna, as a judge, rejected its own proposal), Democratic totalitarianism → 民主极权主义.
- Weak majorities remained: Uniformity → 一律化 (Sol: 整齐划一), Cosmic morale → 宇宙士气 (Sol: 宇宙信念).

### Gemini with the merged glossary

Gemini 3.8 Flash translated chapters 1 and 2 again with the 78-term merged glossary.

- Style was unchanged: 6.13 literary words per 1,000 characters.
- 18 merged terms occur in these chapters, 57 times. Segments using the merged rendering rose from 54 to 56.
- The weak rendering 一律化 was now enforced in both of its segments, and the passage read worse.
- The harmony mistranslation did not recur, but that term is not in the glossary, so the change is run-to-run variation.

## Limits

- One book, one run per model, low effort only. No stability measurement.
- The fidelity judgment rests on three sampled passages; the style judgment rests on one reader.
- The register word lists are rough proxies.
- The comparison scripts and the trimmed EPUB are not in the repository. The output lives in `~/Documents/BookWeaver/Political Thinking - codex trial ch1-2/` on the owner's machine: the side-by-side HTML files, `term-review/merged-glossary.json`, `term-review/aggregate.json` and each judge's raw output.
- `terminology_extraction.max_terms` in the owner's ignored `config/config.json` is now 100. These runs used 50.
