# BookWeaver Superpowers Plans & Issues

This directory contains diagnostic plans, issue analyses, and TDD strategies for BookWeaver development.

## Current Issues

### 🚨 CRITICAL: Prompt Pollution in EPUB Glossary Injection

- **Status**: 🔴 BLOCKED - Awaiting Root Cause Analysis
- **Severity**: CRITICAL  
- **Files**:
  - `ISSUE-PROMPT-POLLUTION-DIAGNOSIS.md` - Full diagnostic report
  - `PLAN-TDD-GLOSSARY-POLLUTION-FIX.md` - TDD strategy
  - Evidence: `copilot-image-9f098c.png` (in parent directory)

**Quick Summary**:
Glossary prompt instructions are being mixed into final EPUB pages instead of being isolated as system prompt only. This affects all glossary-enabled EPUB translations.

**5 Root Cause Candidates**:
1. Glossary block appended to source content (not just prompt)
2. Batch splitting merge logic mixing prompt with content
3. XHTML patching segment indexing errors
4. Gemini API returning prompt in response
5. Recent improvements introducing regression

**Next Action**: Use Claude Opus to analyze and confirm root cause before fixing.

---

## Recent Session Summary

### What We Fixed (Today)
1. ✅ Index separation - bilingual index content split (English/Chinese)
2. ✅ Batch translation splitting - improved robustness for segment count mismatches
3. ✅ Glossary model selection - Pro model always used for glossary extraction
4. ✅ All unit tests passing (216/216)

### What Broke (Today)
1. 🚨 Glossary prompt pollution - prompt directives appearing in translated text

### Lesson Learned
- **Patching symptoms ≠ solving problems**: Fixing three local issues introduced a new architectural problem
- **Need TDD approach**: Must write tests BEFORE changing code
- **Full integration testing required**: Local fixes don't guarantee system-level correctness

---

## Development Approach Going Forward

### Principle: Test-Driven Development (TDD)

Before making ANY code changes:
1. **Write failing test** that reproduces the issue
2. **Confirm test failure** (prove the bug exists)
3. **Implement minimal fix** to pass the test
4. **Run all tests** (ensure no regressions)
5. **Refactor** if needed for code quality

### Files in This Directory

| File | Purpose |
|------|---------|
| `ISSUE-PROMPT-POLLUTION-DIAGNOSIS.md` | Full diagnostic analysis with 5 root cause candidates |
| `PLAN-TDD-GLOSSARY-POLLUTION-FIX.md` | TDD strategy and test case design |
| `README.md` | This file - navigation and context |

---

## How to Use This

1. **For understanding the issue**: Read `ISSUE-PROMPT-POLLUTION-DIAGNOSIS.md`
2. **For implementation strategy**: Read `PLAN-TDD-GLOSSARY-POLLUTION-FIX.md`
3. **For quick reference**: Check the summary sections in this README

---

## Related Documentation

- `docs/architecture/specs/SPEC-010-*.md` - Glossary extraction & injection specification
- `docs/architecture/specs/SPEC-011-*.md` - Model routing & provider factory specification
- `CLAUDE.md` - Developer behavior guide for BookWeaver
- `README.md` - User-facing documentation

---

## Contact & Status

- **Last Updated**: 2026-03-28 23:18
- **Current Blocker**: Root cause analysis (awaiting Opus)
- **Expected Resolution**: After diagnostic phase + TDD test design + implementation

