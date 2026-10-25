# Choose the Canonical Application Seam

Type: grilling
Status: open
Triage: ready-for-human
Blocked by: 01

## Question

What is the smallest deep application interface that should sit between the thin `bookweaver` CLI and the translation implementation, and which orchestration responsibilities must move behind that seam?

The decision must place provider construction, prompt and glossary preparation, checkpoint restore/persist, retry policy, sanity checks, source selection, and output save without turning the new interface into a mirror of the current `ai/cli.py` implementation.

## Comments
