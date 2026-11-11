# BookWeaver Translation

BookWeaver translates long-form publications while preserving reusable completed work and the structure of the publication being translated.

## Language

**Alternating Bilingual EPUB**:
An EPUB publication where each translated block appears immediately following its corresponding source block, preserving full original structure, links, and navigation.
_Avoid_: Dual-language book, parallel text, side-by-side EPUB

**Segment**:
The minimal leaf text block (such as a paragraph, heading, or list item) identified in an EPUB as the atomic unit for translation and bilingual alignment.
_Avoid_: Chunk, passage, unit

**Batch**:
A contiguous sequence of segments grouped together for a single model translation request, bounded by character and segment limits.
_Avoid_: Window, slice, group

**Checkpoint**:
The single, atomically updated document that records completed batches and runtime metadata to guarantee safe resumption of an interrupted run.
_Avoid_: Save file, cache, dump

**Model Profile**:
The logical quality-and-workload tier a translation runs at — flash or pro — independent of which concrete provider model realizes it. It is the unit of resume compatibility.
_Avoid_: Model, model name, alias, lite

**Preset**:
A named, owner-enabled selection of model profile, effort, provider, and concrete model that one run uses.
_Avoid_: Row, mode, model

**Effort**:
How much thinking a preset asks of its model: low, medium, or high. It is a separate choice from the model profile.
_Avoid_: Thinking level, reasoning level

**Runtime**:
The quota pool a run draws on: a local subscription tool or a vendor's paid API.
_Avoid_: Backend, engine

**Metered Preset**:
A preset whose run is billed by a vendor per request. Choosing one never counts as Paid Consent.
_Avoid_: API preset, paid model, metered row

**Paid Consent**:
A person's explicit permission for one run to spend money. It covers that run only and is never stored.
_Avoid_: Authorization, always allow

**Book Library**:
The local collection where each uploaded book stays with its translation and saved progress.
_Avoid_: Workspace, uploads, cache

**Term Extraction**:
The step before translation that fixes the book's key terms and their translations for the whole run.
_Avoid_: Glossary generation, dictionary

**Deep Scan**:
Term Extraction that sends the whole book to a model. It runs only when a person explicitly asks for it.
_Avoid_: Tier 3, full scan

**Term Panel**:
A named set of presets from different vendors that propose and judge the terms for one book; aggregated into a tiered glossary via majority voting.
_Avoid_: Committee, ensemble

**Nominator**:
A Term Panel member that proposes candidate terms with one translation each.
_Avoid_: Extractor

**Judge**:
A Term Panel member that decides, for each candidate, whether to keep it and which translation to use.
_Avoid_: Reviewer, grader

**Term Tier**:
How strictly the translator must use a term: a Fixed Term must always use its exact translation; a Preferred Term is a suggestion the translator may adapt to context.
_Avoid_: Hard/soft constraint, strictness level
