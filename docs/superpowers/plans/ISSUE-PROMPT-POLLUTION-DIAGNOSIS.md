# 🚨 ISSUE: Prompt Pollution in EPUB Glossary Injection

**Status**: 🔴 BLOCKED - Awaiting Root Cause Analysis  
**Severity**: CRITICAL  
**Category**: SPEC-010 Glossary Injection  
**Date Created**: 2026-03-28  
**Evidence**: copilot-image-9f098c.png (Chapter 4 page showing prompt content in translated text)

---

## Problem Statement

**Glossary prompt instructions are being mixed into the final EPUB translation output.**

When translating with `--extract-glossary` flag, the `{GLOSSARY_BLOCK}` content (terminology constraints, negative conditions, etc.) is appearing directly in the translated EPUB pages, instead of being used only as system prompt guidance.

### Symptoms

```
Page content (Chapter 4, "The four pillars of a good unit test"):

【关键本协约点】以下术语须按指格遵守规准译法：
• classical school vs. London school → 经典学派 vs. 伦敦学派
• state-based testing vs. communication-based testing → 基于状态的测试 vs. 基于通信的测试
• mock → 模拟对象 (用于行为验证)
• stub → 桩对象 (用于状态供给)
...
```

These glossary directives should NOT appear in user-visible text. They should only influence the translation process.

### Impact

- 🔴 EPUB readability completely compromised
- 🔴 Every chapter may be affected
- 🔴 Glossary injection feature broken for EPUB workflow
- ⚠️ Possible regression from recent batch splitting improvements

---

## Root Cause Analysis - Candidates

### Candidate 1: Glossary Block Appended to Source Content

**Location**: `ai/epub_translate_roundtrip.py`, `batch_translate()` function

**Mechanism**:
```
┌─ XHTML source segments extracted
│
├─ join_segments_for_batch() combines them
│
├─ Glossary block somehow appended to joined text (NOT just prompt)
│
├─ Full text (source + glossary?) sent to Gemini
│
└─ Gemini translates entire thing, including glossary directives
```

**Check Points**:
- [ ] Is glossary being added to `batch_segments` before joining?
- [ ] Does `join_segments_for_batch()` accidentally include glossary?
- [ ] Is glossary duplicated in both prompt AND content?

---

### Candidate 2: Batch Splitting Merging Prompt with Content

**Location**: `ai/epub_translate_roundtrip.py`, `split_batch_translation()`

**Mechanism**:
The recent improvement to merge split segments (lines 430-441) might be:
1. Receiving translated text that includes prompt echoes
2. Incorrectly merging prompt text with actual translation output
3. The "last resort" merge heuristic is too aggressive

**Check Points**:
- [ ] Does Gemini output include the system prompt as part of response?
- [ ] Is the merge logic accidentally combining prompt fragments with translation?
- [ ] Are there separator issues where glossary block isn't properly delimited?

---

### Candidate 3: XHTML Patching Mixing Prompt Content

**Location**: `ai/epub_package.py`, `patch_xhtml_alternating()`

**Mechanism**:
1. Source XHTML segments are correct
2. Translations are correct
3. But during patching, glossary block content is mixed in as if it were a segment

**Check Points**:
- [ ] Are translations array length mismatches causing wrong segment assignments?
- [ ] Is glossary block accidentally counted as a segment?
- [ ] Are there off-by-one errors in segment indexing?

---

### Candidate 4: Gemini API Returning Prompt in Response

**Location**: Gemini API behavior

**Mechanism**:
1. Glossary block added to system prompt (correct)
2. Glossary block ALSO added to user message by mistake
3. Gemini echoes back the prompt along with translation
4. Response parser doesn't filter out the echo

**Check Points**:
- [ ] Is glossary being added twice - once to system prompt, once to user message?
- [ ] Does raw Gemini response include the prompt instructions?
- [ ] Are there any Gemini API settings that cause echo behavior?

---

### Candidate 5: Recent Improvements Introducing Regression

**Location**: Commits since last working version

**Mechanism**:
The three commits from today:
- `fix(spec-010): separate mixed index content`
- `fix(epub-workflow): improve batch translation splitting`
- `fix(spec-010): glossary extraction always uses Pro model`

One of these may have broken the glossary isolation.

**Check Points**:
- [ ] Does the issue occur with the glossary feature disabled?
- [ ] When was the glossary last working correctly?
- [ ] Did any change affect prompt construction or segment handling?

---

## Required Analysis (Before Fixing)

### Phase 1: Reproduction
- [ ] **Write minimal test case** using a small EPUB section with glossary
- [ ] **Capture raw Gemini response** to see if prompt is included
- [ ] **Inspect batch_translate() inputs/outputs** at each stage
- [ ] **Verify prompt construction** is correct

### Phase 2: Root Cause Confirmation
- [ ] **Trace segment flow**: source → batch → Gemini → split → patch
- [ ] **Check glossary block construction** in GlossaryInjector
- [ ] **Compare working vs. broken version** (if available)
- [ ] **Inspect XHTML patching** for off-by-one errors

### Phase 3: Test Design (TDD)
Before fixing, define:
- [ ] **Test 1**: Glossary terms do NOT appear in translated segments
- [ ] **Test 2**: Glossary constraints ARE respected in translation
- [ ] **Test 3**: Segment count matches before/after translation
- [ ] **Test 4**: Bilingual XHTML doesn't include prompt directives

---

## Debugging Strategy

### Priority 1: Check Glossary Block Isolation
```python
# In batch_translate(), before sending to Gemini:
print(f"[DEBUG] Glossary block:\n{glossary}")
print(f"[DEBUG] Joined segments (first 200 chars):\n{joined_text[:200]}")
print(f"[DEBUG] Full prompt sent to Gemini (first 500 chars):\n{full_prompt[:500]}")

# After Gemini returns:
print(f"[DEBUG] Raw Gemini response (first 500 chars):\n{raw_response[:500]}")
```

### Priority 2: Check Segment Patching
```python
# In patch_xhtml_alternating():
print(f"[DEBUG] Expected segments: {len(segments)}")
print(f"[DEBUG] Got translations: {len(translations)}")
if len(translations) != len(segments):
    print(f"[DEBUG] MISMATCH! Translations: {[t[:100] for t in translations]}")
```

### Priority 3: Binary Search
- Test EPUB workflow WITHOUT glossary → does content look clean?
- Test EPUB workflow WITH glossary but WITHOUT glossary injection in prompt → what happens?
- Test glossary-only extraction → is the JSON correct?

---

## Current Code Paths

### Glossary Injection Points
1. **Loading**: `ai/glossary_injector.py` → `GlossaryInjector.format_block()`
2. **Construction**: `ai/epub_translate_roundtrip.py:717` → builds glossary block
3. **Prompt Building**: `ai/epub_translate_roundtrip.py:117` → appends to prompt
4. **Translation**: `ai/epub_translate_roundtrip.py:145-200` → `batch_translate()` calls Gemini
5. **Response Parsing**: `ai/epub_translate_roundtrip.py:586-445` → `split_batch_translation()`
6. **XHTML Patching**: `ai/epub_package.py:500-550` → `patch_xhtml_alternating()`

### Recent Changes That May Be Related
- `ai/glossary_extractor.py`: Added `_separate_mixed_index()` function
- `ai/epub_translate_roundtrip.py`: Improved `split_batch_translation()` with multiple fallback strategies
- `translatebook.sh`: Changed glossary extraction to always use Pro model

---

## Next Steps

### Do NOT fix yet:
- ❌ Do not modify code
- ❌ Do not attempt patches
- ❌ Do not disable features

### Do this:
- ✅ **Use Claude Opus** to analyze this document + code paths
- ✅ **Write reproduction test** (TDD approach)
- ✅ **Confirm root cause** with evidence
- ✅ **Design minimal fix** that doesn't introduce new regressions

### Timeline
- Phase 1 (Analysis): Immediate (Opus review)
- Phase 2 (Test Design): After cause confirmed
- Phase 3 (Implementation): After tests written
- Phase 4 (Verification): Full workflow test

---

## Related Files

```
ai/glossary_injector.py          - Builds glossary block text
ai/epub_translate_roundtrip.py   - Glossary injection + translation
ai/epub_package.py               - XHTML patching logic
ai/glossary_extractor.py         - Glossary extraction (recent changes)
tests/unit/test_epub_translate_batching.py  - Batch splitting tests
```

## Related Issues

- SPEC-010: Terminology Extraction & Glossary Injection (MVP)
- SPEC-011: Model Routing & Provider Factory
- Recent commits: 3 commits from 2026-03-28

---

## Evidence

**Screenshot**: copilot-image-9f098c.png  
Shows Chapter 4 page with embedded glossary constraint text mixed into readable content.

