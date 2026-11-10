# BookWeaver Translation

BookWeaver translates long-form publications while preserving reusable completed work and the structure of the publication being translated.

## Language

**Supported Product Path**:
An input-to-output translation path that receives the project's full compatibility, safety, documentation, and verification guarantees. EPUB-to-EPUB is currently the only Supported Product Path.
_Avoid_: Main workflow, preferred format

**Isolated Format Capability**:
A non-supported format capability retained for possible future reuse without receiving current product guarantees or constraining the Supported Product Path.
_Avoid_: Supported format, legacy support

**Legacy Workflow**:
An older orchestration path retained only until an explicit retirement or archival decision is made. It receives no new feature or compatibility commitments.
_Avoid_: Alternate pipeline, secondary supported path

**Model Profile**:
The logical quality-and-workload tier a translation runs at — flash or pro — independent of which concrete provider model realizes it. It is the unit of resume compatibility; concrete provider model strings are provenance, not identity. One exception: a resume that crosses a Codex model stops without `--force-resume` (SPEC-025 §3.9).
_Avoid_: model, model name, alias, lite

**Preset**:
A named, owner-enabled selection of model profile, effort, provider, and concrete model that one run uses. It is what a person chooses; the separate settings behind it are not.
_Avoid_: row, mode, model

**Effort**:
How much thinking a preset asks of its model: low, medium, or high. It is a separate choice from the model profile.
_Avoid_: thinking level, reasoning level

**Runtime**:
The quota pool a run draws on: a local subscription tool or a vendor's paid API.
_Avoid_: backend, engine

**Metered Preset**:
A preset whose run is billed by a vendor per request. Choosing one never counts as Paid Consent.
_Avoid_: API preset, paid model, metered row

**Paid Consent**:
A person's explicit permission for one run to spend money. It covers that run only and is never stored.
_Avoid_: authorization, always allow

**Book Library**:
The local collection where each uploaded book stays with its translation and saved progress.
_Avoid_: workspace, uploads, cache

**Term Extraction**:
The step before translation that fixes the book's key terms and their translations for the whole run.
_Avoid_: glossary generation, dictionary

**Deep Scan**:
Term Extraction that sends the whole book to a model. It runs only when a person asks for it.
_Avoid_: Tier 3, full scan

**Term Panel**:
A named set of presets from different vendors that propose and judge the terms for one book; a program, not a model, combines their votes into a tiered glossary (SPEC-028). Users choose a panel by name, never its members one by one.
_Avoid_: committee, ensemble

**Nominator**:
A Term Panel member that proposes candidate terms with one translation each.
_Avoid_: extractor (when several take part)

**Judge**:
A Term Panel member that decides, for each candidate, whether to keep it and which translation to use. A translation judge (SPEC-025 §3.7) is a different role.
_Avoid_: reviewer, grader

**Term Tier**:
How strictly the translator must use a term: a Fixed Term must always use its translation; a Preferred Term is a suggestion the translator may adapt to the sentence. Separate from `priority`, which filters and orders terms.
_Avoid_: hard/soft constraint, strictness level
