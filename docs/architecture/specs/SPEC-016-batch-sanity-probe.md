# SPEC-016: Batch Sanity Probe

**Status:** Draft  
**Date:** 2026-04-05  
**Replaces:** P0-1 (restore `roundtrip_checkpoint/docs/` XHTML artifacts) — that item is dropped; see rationale below.

---

## Problem

After the SPEC-012 hexagonal refactor, the checkpoint system shifted from per-document XHTML files to a flat `translations.json` keyed by segment ID. This is architecturally correct (better fault tolerance, segment-level resume, decoupled render from translate). However, it removed all mid-run translation quality feedback: the user currently sees only batch indices and segment counts — zero translated text — until the entire book is done.

The real risk is not "I can't read the intermediate XHTML" — it is **runaway model failure going undetected**: wrong-language output, repetition loops, empty responses. These burn API tokens silently across many batches before the user notices.

**Goal:** Halt the pipeline at the first batch where model output is clearly wrong. Save tokens. Give the user enough mid-run signal to know the model is healthy.

---

## Non-Goals

- Restoring `roundtrip_checkpoint/docs/` XHTML intermediate files — this re-couples translation and rendering. Dropped.
- Translation quality scoring (style, terminology) — that is a human pre-flight / post-run concern, not a runtime gate.
- Statistical quality metrics (BLEU, etc.) — deferred to SPEC-015 Phase 3 / future quality module.

---

## Design

### Checks (per-segment, applied to every segment in each completed batch)

| Check | Condition | Notes |
|---|---|---|
| **Empty output** | `len(translated.strip()) == 0` | Always applied |
| **Length ratio** | `min_ratio ≤ len(translated) / len(source) ≤ max_ratio` | Skipped when `len(source) < min_source_length` (short segments produce unreliable ratios) |
| **CJK density** | `cjk_count(translated) / len(translated) ≥ min_cjk_density` | Only when `output_lang` starts with `"zh"`. Guards against model returning untranslated English. |

CJK character range: `\u4e00–\u9fff` (CJK Unified Ideographs), sufficient for the guard use-case.

### Heartbeat Sample

After each batch passes checks, emit one `[progress:batch_sample]` line showing the first segment's source and translation (truncated to `heartbeat_chars`):

```
[progress:batch_sample] batch=3/22 doc=EPUB/ch04.xhtml src="The key principle is..." tgt="核心原则是..."
```

This is a passive heartbeat — not interactive, not blocking. The user can glance at it in the terminal to confirm the model is producing sane output.

### Failure Behaviour

On first failing segment within a batch:
- Raise `TranslationError` with the segment ID, batch position, and failing check + measured value.
- Example: `sanity check failed at batch 3/22 — cjk_density=0.05 < 0.30 (segment EPUB/ch04.xhtml::42)`
- Pipeline halts. The checkpoint already contains all segments from batches 1–2 (persisted after each batch), so `--resume` will restart from batch 3.
- No partial batch is written to the checkpoint.

### Configuration

New top-level key in `config.json` / `config.json.example`:

```json
"sanity_probe": {
  "enabled": true,
  "max_length_ratio": 2.0,
  "min_length_ratio": 0.15,
  "min_source_length": 10,
  "min_cjk_density": 0.30,
  "heartbeat_chars": 60
}
```

**Threshold rationale:**
- `max_length_ratio = 2.0`: EN→ZH normal ratio is 0.2–0.6 chars. Even short/idiomatic phrases rarely exceed 1.5×. 2.0 catches repetition loops (model echoing translated text) before they burn significant tokens.
- `min_length_ratio = 0.15`: Guards against severe truncation; allows legitimately short translations.
- `min_source_length = 10`: Avoids ratio false-positives on one-word or single-character source segments.
- `min_cjk_density = 0.30`: Requires at least 30% CJK characters in output. Rejects "照抄英文加中文句号" (copy-paste English + one Chinese punctuation mark) and fully-English responses.
- `heartbeat_chars = 60`: Enough context to visually verify without flooding the terminal.

`enabled: false` disables all checks and suppresses the heartbeat line (for non-ZH workflows or CI environments where output is noisy).

### Implementation Location

All logic in `ai/cli.py`:

1. Load `sanity_probe` config block alongside existing config loading (with defaults as above).
2. Add `_sanity_check_batch(segments, output_lang, probe_config) -> None` helper — raises `TranslationError` on failure.
3. Add `_heartbeat_sample(batch_index, total_batches, batch_segments, probe_config)` helper — emits `[progress:batch_sample]` line.
4. Call both from `_persist_batch` callback, before writing to checkpoint.

No new modules. When SPEC-015 introduces a quality scoring subsystem, extract the check logic into `ai/core/quality.py` at that time.

### Execution Order in `_persist_batch`

1. **Sanity check** — iterate segments, run checks in order: empty → length ratio → CJK density. Raise `TranslationError` on first failure (empty check must precede CJK density check to avoid division-by-zero).
2. **Heartbeat sample** — emit `[progress:batch_sample]` for first segment.
3. **Persist** — accumulate translations and write checkpoint.

### CLI Flag

`--no-sanity-probe` disables all checks and the heartbeat for the current run (equivalent to `"enabled": false` in config). Note: the CJK density check already auto-skips for non-ZH runs; `--no-sanity-probe` additionally disables the empty and length ratio checks.

---

## Impact on Other Work

| Item | Impact |
|---|---|
| P0-1 (restore docs/ XHTML) | **Dropped.** This SPEC addresses the actual underlying need. |
| SPEC-015 quality scoring | Natural evolution point: when quality scoring lands, extract probe logic into `ai/core/quality.py` and wire in SPEC-015 thresholds. |
| SPEC-013 pipeline completion | No conflict. Probe lives in `ai/cli.py` which is the boundary between shell and engine. |

---

## Acceptance Criteria

1. Running translation with a mocked provider that returns empty strings → `TranslationError` raised at batch 1.
2. Running with a provider that returns wrong-language text (English only) → `TranslationError` with `cjk_density` reason.
3. Running with a provider that returns a 10× repeated string → `TranslationError` with `length_ratio` reason.
4. Normal EN→ZH translation passes all checks without false positives.
5. `[progress:batch_sample]` line emitted once per batch (first segment only).
6. `--no-sanity-probe` suppresses all checks and heartbeat.
7. `"enabled": false` in config has same effect as `--no-sanity-probe`.
