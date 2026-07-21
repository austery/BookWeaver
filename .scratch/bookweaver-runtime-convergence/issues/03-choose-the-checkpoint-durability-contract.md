# Choose the Checkpoint Durability Contract

Type: prototype
Status: open
Triage: ready-for-human
Blocked by: 01

## Question

Which persistence model should guarantee segment-level resume and crash consistency across checkpoint metadata and translations: a single checkpoint document, generation directories with an atomic current pointer, a journal, or an explicitly tolerated two-file consistency window?

The decision must cover schema-v1 migration, mixed-provider provenance, partially written generations, no-op full resume, and recovery behavior without allowing checkpoint state to grant paid API authorization.

## Comments
