# Chapter 1 Flash A/B Report (The Fault in Our Stars)

## Scope

- Book: `/Users/leipeng/Documents/Calibre_Books/John Green/The Fault in Our Stars (92)/The Fault in Our Stars - John Green.epub`
- Chapter doc: `OEBPS/9781101569184-8.html` (narrative Chapter 1)
- Slice: first 24 segments
- Model: `gemini-2.5-flash`
- A/B variable:
  - A = immersive prompt (`build_system_prompt(..., immersive=True)`)
  - B = simplified prompt (`build_system_prompt(..., immersive=False)`)
- Fixed:
  - same segment set
  - same model
  - same provider path
  - same batching

## Runtime telemetry

- Segments: `24`
- A calls: `1`
- B calls: `1`
- A split retries: `0`
- B split retries: `0`
- A elapsed: `15.2s`
- B elapsed: `24.5s`

## Full corpus (Source + A + B)

Segment corpus is included in a companion file.
Companion: `docs/plans/2026-04-03-chapter1-flash-ab-full-corpus.md`
