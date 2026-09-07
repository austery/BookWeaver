# PR #25 v1 feedback response

Reviewed head: `4b44eb8be041b4810af34b4e747ab34c2c7680ee`. This response describes uncommitted local remediation; it does not replace or amend the historical review. The remote head was rechecked and still matches that commit. GitHub currently reports the PR as ready for review, not draft; no state change was made here.

| Review item | Evidence | Decision | Next action |
| --- | --- | --- | --- |
| F1: authentication false success | Reran the supplied offline executable reproduction: three calls and authentication text persisted. New singleton/multi-segment regressions failed before the fix and pass afterward. | Accept | Recognize the documented terminal response before protocol parsing; one typed authentication failure, no output/checkpoint. |
| F2: metadata-only identity | Reran same-length content mutation with preserved timestamps; old translations restored. New mutation and moved-identical-input regressions failed before the fix and pass afterward. | Accept | Use streamed SHA-256 of file bytes for active EPUB identity and glossary cache keys. Keep legacy fingerprint handling separate. |
| F3: glossary before validation | Reran the supplied mismatch reproduction: one glossary request preceded rejection. New hard-mismatch/corrupt-document cases pass with zero additional provider requests. | Accept | Validate the checkpoint document and hard fields under the run lock before extraction; validate prompt-dependent compatibility afterward. |
| F4: silent Markdown output | Reran ordinary Markdown input reproduction: empty successful output. File/empty-directory regressions failed before the fix and pass afterward, preserving existing destinations. | Accept | Require a numbered-page directory with translatable segments; do not reinterpret a file as its parent directory. |

## Compatibility consequence

Early v2 checkpoints contain only metadata fingerprints and are rejected against the new `sha256:` content identity, including with force. Preserve those artifacts and select a new checkpoint directory. Legacy v1 imports require a matching legacy fingerprint and explicit force acknowledging unverified historical bytes; imported records retain `source_verification: legacy_metadata_only`. A newly saved v2 identity binds subsequent resumes to current bytes, but does not assert that historical translated segments were content-verified. Legacy files remain untouched.

## Additional evidence

- Cross-provider interrupted resume retains CLI/API model provenance per segment; a fully restored production API invocation makes no paid client construction or authorization request and does not rewrite its checkpoint.
- A directory-fsync failure after replacement raises a persistence error; reopening sees a complete new document. This establishes ordinary process recovery, not power-loss durability after a failed sync.
- Main and standalone glossary paths are exercised through a replaced SDK client for denied, failed, and successful requests. Denial constructs no client; a transport failure attempts once; successful main translation calls Pro glossary followed by Flash body and preserves usage counts.
- No live models, paid requests, or real book transmission were used for this remediation.

## Remaining scope

Spec conformance remains partial. Representative whole-book quality/layout acceptance, legacy retirement, schema-consumer parity, invocation-wide discovery/provenance refinements, explicit CLI exit mapping and paid-volume UX, and other unimplemented coverage in the original review are not claimed complete by this patch. The original review remains unchanged.

## Verification

The eight initial public regressions failed before implementation and passed afterward. Targeted review/checkpoint tests passed. Ruff lint/format, Tach architecture checks, changed-module compilation, retained shell syntax, and Git whitespace checks passed. **Full current-tree regression: 573 passed, 1 skipped in 166.74 seconds.** No commit, push, or GitHub review submission was made.
