# TDD Plan: Fix Prompt Pollution in EPUB Glossary Injection

**Phase**: 待强模型诊断 (Awaiting Opus Analysis)  
**Status**: BLOCKED  
**Owner**: Lei (with Opus review)

---

## 📋 Quick Summary

**Problem**: Glossary prompt instructions are being mixed into translated EPUB pages  
**Root Cause**: TBD - 5 candidates identified  
**Evidence**: copilot-image-9f098c.png  
**Approach**: TDD - Write tests before fixing

---

## Test Cases to Write (Before Fixing)

### Test Suite 1: Glossary Block Isolation
```
✓ Test: Glossary block is NOT included in segment content
✓ Test: Glossary block is ONLY in system prompt
✓ Test: Translated segments don't contain glossary directives
```

### Test Suite 2: Segment Count Accuracy
```
✓ Test: Input segments count == output translations count
✓ Test: No off-by-one errors in XHTML patching
✓ Test: Glossary block is not counted as a segment
```

### Test Suite 3: XHTML Content Integrity
```
✓ Test: Bilingual XHTML doesn't include prompt text
✓ Test: All glossary terms are respected in translation (semantic check)
✓ Test: Original segment boundaries preserved in output
```

### Test Suite 4: End-to-End EPUB Quality
```
✓ Test: Full EPUB roundtrip without glossary pollution
✓ Test: Glossary-enabled and glossary-disabled produce same content
✓ Test: Chapter structure and headings preserved
```

---

## Debugging Checkpoints

1. **Glossary Block Construction**
   - [ ] GlossaryInjector.format_block() output correct?
   - [ ] Format block properly formatted as prompt text?

2. **Prompt Assembly**
   - [ ] _create_translation_prompt() doesn't duplicate glossary?
   - [ ] System prompt + user message correctly separated?

3. **Segment Joining**
   - [ ] join_segments_for_batch() includes glossary?
   - [ ] Raw joined text sent to Gemini correct?

4. **Gemini Response**
   - [ ] Raw response includes prompt echo?
   - [ ] Response parser handles glossary text?

5. **Batch Splitting**
   - [ ] split_batch_translation() merging logic correct?
   - [ ] Merge heuristic accidentally combining prompt fragments?

6. **XHTML Patching**
   - [ ] patch_xhtml_alternating() segment index off-by-one?
   - [ ] Translation array matches segment array?

---

## Files to Investigate

Priority Order:

1. 🔴 `ai/epub_translate_roundtrip.py` (lines 100-120, 586-445, 807)
   - Prompt construction
   - Batch splitting merge logic
   - Glossary parameter passing

2. 🟡 `ai/epub_package.py` (lines 500-550)
   - XHTML patching logic
   - Segment indexing

3. 🟡 `ai/glossary_injector.py` (lines 43-66)
   - Block formatting

4. 🟢 `tests/unit/` 
   - Current tests (should have caught this)
   - New TDD tests (preventative)

---

## Expected Fix Complexity

- **Best Case**: Configuration issue or simple string handling (30 min)
- **Medium Case**: Segment indexing logic (2-4 hours)
- **Worst Case**: Architectural redesign of prompt/content separation (1 day)

---

## Success Criteria

- ✅ All new TDD tests pass
- ✅ EPUB generated with NO glossary prompt text visible
- ✅ Glossary constraints still respected in translation
- ✅ No regression in other SPEC-010/011 features
- ✅ 100% of old tests still pass

---

## Prevention

After fix:
- Add glossary+EPUB integration test to CI/CD
- Document prompt/content separation boundaries
- Add debug logging for glossary injection

