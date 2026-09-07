# Stoic Joy: first full-book Antigravity validation

## Outcome

The complete EPUB translation and checkpoint recovery succeeded. **Translation-quality acceptance is not met**: the 27-passage review found one unsupported causal addition and one age-range precision issue. This is a review candidate, not a claim that SPEC-021 is complete.

Output: `output/stoic-joy-20260907/A Guide to the Good Life - bilingual.epub`.
Detailed local evidence, including bilingual review samples, resides in the same ignored output directory. No book text, credentials, or generated EPUB was committed or pushed.

## Reproducible configuration

- Source: William B. Irvine, *A Guide to the Good Life: The Ancient Art of Stoic Joy*, user-selected Calibre EPUB.
- Source SHA-256: `e3ddd13211691930f3af1b212649b109ebbbf160d275b9c2eab452c367f8485f` (unchanged after the run).
- Code: merged `fc5a064`; no implementation changes during this test.
- Antigravity CLI version recorded per translated segment: `1.1.27`.
- Body: `gemini-3.8-flash-low`, explicit effective effort `low`; subscription runtime only.
- Glossary: `gemini-3.1-pro-low`, index-based extraction, maximum 50 terms, 17 terms returned.
- Input: 2,061 extracted segments, 481,103 source characters, 357 spine documents, 5 image resources.
- Protocol: `segment_tags`; segmenter: `epub-leaf-block-v3`; batch size: 60,000 source characters, separator overhead 6.
- Effective prompt SHA-256: `6f0b04ca835789eb89a8632a6d2269e441764c7607d59d9a6fef850df0d291a4`.
- Added instruction: `Preserve numerical and temporal facts exactly. Interpret ordinal decades of a persons life correctly: the fifth decade means ages 40–49, not turning 50. Do not add factual specificity absent from the source.`
- Existing local configuration disables the runtime sanity probe. It was preserved; default, stricter sanity thresholds were applied independently after translation.
- No metered Gemini API request occurred.

The exact body model identity is the requested/recorded CLI identity; this is not independent server-side model attestation.

## Sample and full-run procedure

A separately packaged introduction sample retained its chapter/resources and removed out-of-sample links. The initial 38-segment sample mistranslated “fifth decade” as entering age fifty. The explicit temporal instruction above corrected this on the second sample run, and the full book also renders the age as the forties. This correction does not certify the unmodified default prompt.

The full run used the actual CLI composition and actual Antigravity provider. A local harness logged source-text hashes at the real provider boundary and sent SIGINT immediately after the second successful atomic save, before starting another provider call. It resumed all 240 committed segments and requested only the remaining seven planned batches. This tests interruption at a durable batch boundary, not mid-request child-process termination.

- Full book: **9 body requests + 1 glossary request**. No split retries.
- Planned body segment counts: 143, 97, 92, 108, 96, 99, 95, 919, 412. Exact request hash sequences matched the original batch plan across both invocations.
- Active elapsed time: 171.80 seconds before controlled interruption + 548.24 seconds for continuation = **720.04 seconds**, excluding sample generation and review time.
- The 919-segment batch was noticeably slower than ordinary prose batches; character count alone does not represent framing overhead.
- Final checkpoint: 1,223,510 bytes; final save about 0.0139 seconds. File rewrite cost was small in this run.
- A third, fully restored invocation requested zero provider calls and left checkpoint bytes and modification time unchanged.

## Structural and visual evidence

The final output has all 2,061 translations, exact checkpoint segment-ID order, and zero blank translations. ZIP entry names/order, original element IDs, and non-document resources match the source. After removing only injected translation blocks/style, every original document DOM matches its source. Package checks report no errors or missing assets. Fragment-link validation reports zero broken links in either source or output.

A Calibre PDF rendering of the corrected introduction was visually inspected: English/Chinese alternation and Chinese glyphs were readable, without observed overlap or clipping on the inspected page. Native EPUB-reader automation could not reliably complete file selection. Full-book reader navigation, footnote activation, and layout inspection are therefore **not certified** by this run. Structural integrity is separate evidence.

Output SHA-256: `ff2cd06bb068554c164a07ffcf6687c4ed6be9c91af92e4301f3e4ada4b660c0`.

## Quality findings

The 27 predefined samples cover 23 prose documents plus the previously failed age passage, two notes, and an index entry. Source/translation pairs and per-passage observations are in `reviewed-passages.json`.

1. **Unsupported addition — `text/part0028.html::6`:** the source says Seneca behaved in a way that brought a death sentence when he could have avoided doing so. The target supplies offending powerful people as the mechanism. This extra causal claim is not present in the source. It remains unedited in the delivered model output.
2. **Precision — `text/part0027.html::11`:** “eighties” and “twenties” become age eighty and twenty rather than ranges. The targeted fifth-decade correction did not establish general numeric-expression fidelity.
3. **Bibliography duplication:** all 60 bibliography segments were copied verbatim as translations, creating duplicate English bibliography paragraphs. Preserving citation metadata may be useful, but duplicating it as a bilingual block is a product/prompt policy gap.
4. **Sanity classification:** stricter default checks flagged 131 segments: 60 unchanged bibliography entries, 61 numeric-heavy index entries, and 10 numeric-heavy notes. The latter 71 were inspected and their low CJK density reflects retained references/page numbers, not missing Chinese prose. A uniform CJK threshold is poorly suited to these segment types.
5. **Correction to interim commentary:** the observed Seneca-name difference was between the introduction sample and full run, not within the final book. The final checkpoint has “塞涅卡” in 194 segments and “塞内加” in zero segments. Do not record an internal name-consistency defect from that observation.

No other material semantic error was observed in the 27 selected passages. This is bounded sampling, not exhaustive semantic proofreading. The unsupported addition is sufficient to fail the zero-material-error sample gate.

## Next work

Use these concrete findings to refine fidelity checks and bibliography handling before claiming quality acceptance or expanding unattended multi-book runs. Preserve this raw output as the baseline. Remaining SPEC-021 work, including complete reader-layout acceptance, other book categories, and gated legacy retirement, remains open.
