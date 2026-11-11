# Workflow Naming and Default Strategy Design

Date: 2026-03-21
Project: BookWeaver
Status: Approved

## 1. Problem

Current UX causes mode confusion:

- Users expect EPUB-first behavior to prioritize package fidelity.
- Existing command examples often trigger markdown-first workflow unless explicit EPUB package mode flags are used.
- Term `roundtrip` is engineering-oriented and not intuitive for product-facing CLI/docs.

## 2. Approved Product Direction

Primary direction is EPUB fidelity first.

- For EPUB input, default workflow should be EPUB package-preserving path.
- Markdown workflow remains available, but as secondary/legacy path.
- Naming must be user-intuitive and avoid `roundtrip` as primary user-facing term.

## 3. Why Markdown Workflow Is Still Kept

Markdown workflow remains valuable for:

1. Non-EPUB source normalization (PDF/DOCX).
2. Stable chunk/resume debugging path.
3. Historical regression comparison against prior outputs.

It is not retained as the preferred EPUB-quality path.

## 4. Naming Contract (User-Facing)

Use workflow-oriented naming instead of engineering terminology.

- Preferred CLI surface: `--workflow epub|markdown`
- Product wording:
  - `epub`: EPUB package-preserving workflow
  - `markdown`: Markdown conversion workflow

`roundtrip` may remain temporarily in internal implementation comments/logs during migration, but target state is to replace it broadly in user-facing and most code/doc wording.

## 5. Behavior Contract

Approved behavior policy:

1. EPUB input defaults to `workflow=epub`.
2. Non-EPUB input defaults to `workflow=markdown`.
3. Users can explicitly force workflow via `--workflow`.
4. Markdown workflow remains supported as explicit fallback/debug path.

## 6. README Information Architecture

README should be restructured to reduce ambiguity:

1. Add a top-level mode selection table (Input type x Goal x Recommended workflow).
2. Show shortest "happy-path" commands first.
3. State defaults explicitly and early.
4. Explain output artifacts per workflow with concrete paths.
5. Keep advanced flags and migration notes in lower sections.

## 7. Migration Notes

Transition should prioritize compatibility:

- Keep existing flags temporarily with deprecation notes.
- Add clear mapping table from old flags to `--workflow`.
- Ensure help text and dry-run output clearly report resolved workflow.

## 8. Out of Scope (This Design Only)

- No immediate code changes in this design step.
- No removal of markdown pipeline in current phase.
- No deep refactor of translation internals yet.

## 9. Acceptance for This Design

Design is considered successful when:

- Team/user can explain when to choose each workflow in one sentence.
- Default behavior expectation for EPUB is unambiguous.
- User-facing wording no longer depends on `roundtrip` terminology.
