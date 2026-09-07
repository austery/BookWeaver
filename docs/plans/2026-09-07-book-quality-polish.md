# Book quality polish after the first full-book run

Owner approved these three follow-ups; Codex comparison/integration is deferred.

1. Preserve dedicated bibliography documents as source-only. Recognize explicit body bibliography semantics or an exact leading bibliography heading; do not infer this from filenames or a mention in prose. Extraction and patching must agree. Version the active EPUB segmentation policy; older checkpoints fail the hard segmenter check rather than silently losing records.
2. Add an adjustable 200-segment default cap for active EPUB translation, alongside the existing 60,000-character limit. Carry the effective cap through CLI/config, application, engine, and checkpoint identity. Changes are soft compatibility mismatches. Legacy identities lacking this field mean no segment cap, not an invented default.
3. Revisit chapters 5, 17, and 18 of the selected Stoic Joy EPUB with the same Flash 3.8 Low runtime. Preserve quantities/ranges, negation scope, and causal strength using a general fidelity instruction. Review targeted passages against their source; a model's revised output is not proof of correctness. Rebuild a separate reviewed EPUB from the original source, retain unaffected translations, omit bibliography duplication, and record changed segment provenance outside the original checkpoint.

Keep the original publication, original generated output, and checkpoint untouched. This is a focused usability increment, not completion of all SPEC-021 gates or a claim of exhaustive literary proofreading. No paid API calls, Codex benchmark, commit, push, or merge is authorized by this implementation request.

## Implementation and live result

- Runtime: Antigravity 1.1.27, `gemini-3.8-flash-low`, low effort. No Codex benchmark or paid API invocation.
- Selected documents: chapter 5 (`text/part0014.html`, 39 segments), chapter 17 (`text/part0027.html`, 23), chapter 18 (`text/part0028.html`, 13).
- One real translation batch, 75 segments, 53.80 seconds; public application composition with the existing 17-term glossary and sanity probe enabled. No new glossary extraction. The raw sample checkpoint retains model/prompt/provenance evidence.
- Reviewed 31 source/target passages: chapter 5 indices 0, 2, 3, 5, 7, 10, 12, 15, 20, 25, 30, 35, 38; chapter 17 indices 3, 6, 10, 11, 14, 16, 18, 19, 22; chapter 18 indices 0, 1, 6, 7, 8, 9, 10, 11, 12. Review focused on numbers, negation, control distinctions, explicit versus inferred causes, and possibility versus certainty.
- Confirmed the two prior defects were corrected in fresh model output: chapter 17 index 11 preserves age decades; chapter 18 index 6 no longer supplies an unstated political cause for Seneca's death sentence.
- Four editorial adjustments followed source comparison: chapter 17 index 6 uses a neutral description of death before reaching old age; indices 18 and 19 avoid categorical claims that mortality cannot cause depression; chapter 18 index 7 restores the explicit possibility qualifier on the historical interpretation. These are assistant editorial corrections, not another model benchmark. Raw model results remain unchanged. The final sample has no identified material errors within this targeted review; it is not exhaustive proofreading.

## Revised publication and evidence

Local artifact directory: `output/stoic-joy-polished-20260907/` (ignored, book content is not committed).

- `A Guide to the Good Life - bilingual reviewed.epub`: complete revised publication.
- `revision-ledger.json`: exact source/output/checkpoint hashes, old/new/final text for the 75 revised segments, four editorial corrections, and removed bibliography translation IDs.
- `sample-checkpoint.json`: preserved raw selected-chapter runtime checkpoint.
- `translation-map.json`: derived output validation data, **not a runtime checkpoint** and not suitable for resume.
- `reviewed-passages.json`: the 31 raw model/source pairs; final editorial adjustments are in the ledger.
- `fidelity-prompt.txt`, `run.json`, `run.log`: exact instruction and execution evidence.
- `structural-validation.json`: full-publication structural checks.

The rebuilt book retains 1,926 previous translations and replaces 75 selected-chapter translations, for 2,001 translation blocks. The 60 previous bibliography translation blocks are omitted; bibliography document `text/part0036.html` is byte-identical to the original. Reconstruction verified that every sampled source segment matches the original source text. The original source, prior output, and checkpoint were preserved.

Source SHA-256: `e3ddd13211691930f3af1b212649b109ebbbf160d275b9c2eab452c367f8485f`.

Revised EPUB SHA-256: `e6d953ed85e90d664cd1943b2e7054a759b0a1ffb64884b99b3e58d9c0afed5e`.

Structural results: unchanged ZIP entry names/order, unchanged non-document resources, identical original DOM after removing intended bilingual additions, preserved source IDs, zero missing assets, zero broken links, zero blank translations, and exact segment-ID order. This does not replace full visual acceptance in an EPUB reader.

With the new policy, an offline full-book batch plan is 14 batches, with segment counts `143, 97, 92, 108, 96, 99, 95, 200, 200, 200, 200, 200, 200, 71`. This is planning evidence only; the full book was not retranslated and no throughput improvement is claimed.

## Verification and remaining scope

The complete suite passed with **584 passed, 1 skipped**. Two additional checkpoint/EPUB artifact regression tests were then added; the focused policy suite passed **13 tests**. Coverage includes simultaneous limits and ordering, invalid caps, config and CLI precedence, dedicated versus mixed bibliography detection, exact bibliography-byte preservation, and historical missing-cap compatibility. Ruff lint/format, Tach architecture checks, compilation of changed Python modules, shell syntax, and `git diff --check` all passed. A separate final diff review checked policy boundaries, effective CLI/config flow, and checkpoint compatibility; no remaining blocking implementation issue was identified. This was a self-review, not an external PR review.

README, contributor notes, and SPEC-021 now distinguish delivered book evidence from aggregate acceptance. The original full-book report remains historical evidence; this report supersedes its selected-chapter defects and bibliography duplication for the revised artifact only. Other passages remain inherited from the initial run. Additional titles, full reader/layout acceptance, full configuration/CLI coverage, and legacy retirement remain open. Codex comparison stays deferred.

PR preparation verification: the final complete suite passed with **586 passed, 1 skipped** in 166.59 seconds. The skipped test is the opt-in external-book fixture regression. Ruff lint/format, Tach, changed-module compilation, shell syntax, and whitespace checks passed again.
