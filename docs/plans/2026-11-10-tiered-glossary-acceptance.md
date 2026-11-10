# Tiered glossary acceptance (2026-11-10)

**Result:** the owner adopted tiered glossaries (SPEC-028 Phase 1). The tiered version kept every fixed term, and it scored the highest literary register of three runs. This closes issue 82.

## Setup

- Source: *Political Thinking*, file `ch007.xhtml` only (137 segments, about 95,000 characters). The full book's preferred terms are densest there: 15 distinct terms in 35 segments.
- Translator: `agy-flash-low` (Gemini 3.8 Flash, low effort), product code at `a3e0c6e`, one run per version, about 4 minutes each. Subscription only.
- Glossary: the 91 terms both judges kept in the second-round cross-review (`2026-11-09-translation-evaluation-method.md`). 59 terms where both judges agreed and both said `fixed`; 32 others.
- Versions, one variable:
  - **Strict:** all 91 terms without `tier`, so all strict; no alternatives in the prompt.
  - **Tiered:** the same 91 terms; 59 `fixed`, 32 `preferred`, 15 of them with one alternative from the other judge.
  - **Strict rerun:** the strict version again, to measure run-to-run variation.

The decision gate was written before the run (SPEC-028 §6 item 1): no fixed drift in the tiered version, no register drop, and the owner does not prefer the strict version.

## Results

| Version | Literary per 1,000 | Colloquial per 1,000 | Fixed terms used | Preferred terms used |
|---|---|---|---|---|
| Strict | 6.15 | 9.80 | 30 of 30 | 30 of 35 |
| Tiered | 7.33 | 9.08 | 29 of 30 | 29 of 35, plus 3 with the listed alternative |
| Strict rerun | 6.69 | 9.54 | 30 of 30 | 30 of 35 |

- **Fixed drift:** none in substance. The one miss is Consent of the Governed: the tiered version wrote 经被治者同意 instead of 被治者的同意. The translation is the same; the substring check missed it.
- **Register:** the two strict runs differ by 0.54. The tiered run is 0.64 above the higher strict run. This is one run per setting, so it is an indication, not a measurement of effect size.
- **Size of change:** mean per-segment text similarity was 0.814 between the two strict runs and 0.772 between strict and tiered. Tiers changed some wording beyond the terms, modestly.
- **Alternatives used:** Ortega y Gasset twice as 何塞·奥尔特加-加塞特, and Transcendence once as 超越者. Both were judge-approved alternatives.
- **Owner:** read the 35 segments side by side and chose the tiered version.

## Side findings

- The earlier register drop on chapters 1 and 2 (5.53 and 5.98 with the same 91 terms) did not recur here: strict ch007 scored 6.15 and 6.69. The chapter, not the glossary size, more likely explains it.
- Essentially Equal (本质上平等) and Essentially Superior (本质上优越) missed in every version. They are phrases that bend to fit a sentence (在本质上是平等的), so they are poor glossary terms. That is a term-selection problem for Phase 2, not a tier problem.
- The substring check in `term-consistency.json` cannot see an inflected use of a fixed term. Treat a single fixed miss as a prompt to read the segment, not as proof of drift.

## Not proven

- One book, one chapter, one run per version, one translator.
- Effect on books whose terms are mostly established technical terms.
- Term extraction still writes no tiers; Phase 2 does.

## Files (owner machine)

`~/Documents/BookWeaver/Political Thinking - ch007 tier test/`: the trimmed EPUB, `glossary-strict.json`, `glossary-tiered.json`, one folder per version with its checkpoint and `term-consistency.json`, and `ch007-tier-comparison.html`.
