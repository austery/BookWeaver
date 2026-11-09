# ADR-0003: The product is EPUB in, alternating bilingual EPUB out

Status: Accepted (2026-11-09). The owner approved it by merging PR 77.

## Context

BookWeaver has had Markdown and PDF paths, and it could grow into a general translation tool.

## Decision

EPUB-to-EPUB with alternating source and translation is the only supported product path. The local API serves the owner only.

## Reason

"The owner decided on 2026-11-08 to keep BookWeaver focused: EPUB in, alternating bilingual EPUB out." (issue #53)

The reason for removing DOCX: Reason not recorded.

## Alternatives

A general translation platform and a web or document translation plugin. The North Star lists both as non-goals.

## Consequences

Other formats get no compatibility commitment. Opening the local API to other products needs a new owner decision.
