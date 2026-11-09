# BookWeaver Comprehensive PR Review Fixes — Design Document

**Date**: 2026-03-16
**Author**: Claude Code (Brainstorming + Design)
**Status**: Approved for Implementation
**Scope**: One-shot comprehensive refactoring of all 12 issues from PR review

---

## Executive Summary

BookWeaver's recent PR review identified **12 issues** across code quality, testing, documentation, and configuration. This design document outlines a **one-session, logic-partitioned commit strategy** to fix all issues while maintaining code quality and passing all verification gates.

**Key Decision**: 7 logically-ordered commits, each independently verifiable, enabling clear git history and incremental validation.

---

## Problem Statement

### Issues Identified

| Priority | Category | Count | Impact |
|----------|----------|-------|--------|
| Critical | Code Quality | 4 | Violates CLAUDE.md rules, masks bugs |
| Important | Type Safety | 1 | 60+ untyped functions violate "No Untyped Code" rule |
| Important | Test Coverage | 1 | 8 critical test gaps (error handling, edge cases) |
| Important | File I/O | 1 | Missing error handling in data transformations |
| Important | Configuration | 1 | Ruff ignore list too permissive |
| Suggested | Code Cleanup | 3 | Duplicate imports, unclear code |
| Suggested | Documentation | 1 | Dead code, misdocumented behavior |

### Root Causes

1. **Incomplete migration from Claude CLI → Gemini CLI**: Dead code (`translate_with_claude_cli`, `check_claude_cli`) creates confusion
2. **Inconsistent type annotation across modules**: New `ai/` modules well-typed, but pipeline scripts untyped
3. **Transitional ruff config**: Temporary baseline ignores real issues like bare `except:`
4. **Test gaps from rapid development**: New features added without full edge-case coverage
5. **Documentation drift**: CLAUDE.md has outdated model selection sequence

---

## Solution Design

### Strategy: Logic-Partitioned Commits

Each commit handles one logical concern, is independently verifiable, and can be tested in isolation.

**Why this approach**:
- ✅ Clear git history for future debugging
- ✅ Each commit passes all verification gates (ruff, pytest, syntax)
- ✅ Easy to bisect if future bugs appear
- ✅ If session interrupted, completed commits are mergeable

### Commit Plan

#### Commit 1: Remove Dead Code
**Files**: `03_translate_md.py`
**Changes**:
- Delete `translate_with_claude_cli()` lines 338-530 (193 lines)
- Delete `check_claude_cli()` lines 39-59 (21 lines)

**Why**: Code is unreachable in Gemini-only backend. Confuses maintainers about actual runtime behavior.
**Verification**: pytest, ruff check, syntax compile

---

#### Commit 2: Fix Lockfile Violation (pip → uv)
**Files**: `translatebook.sh`
**Changes**:
- Line 189: Replace `pip install -r "$requirements_file"` with `uv sync` or `uv pip install -r "$requirements_file"`
- Line 192: Replace `pip install python-docx PyMuPDF ...` with `uv pip install python-docx PyMuPDF ...`

**Why**: Violates global CLAUDE.md rule 4 "Lockfiles are Sacred". Project manages deps via `uv.lock`.
**Verification**: `bash -n translatebook.sh` (syntax check)

---

#### Commit 3: Improve Error Handling and Add Logging
**Files**: `03_translate_md.py`, `04_merge_md.py`, `06_add_toc.py`, `07_generate_formats.py`, `tests/unit/test_*.py`
**Changes**:

**3a. Remove bare `except:` clauses**:
- `03_translate_md.py:791-792`: Change bare `except:` to `except Exception:` with log message
- `06_add_toc.py:481`: Change bare `except:` to `except Exception:` with log message

**3b. Add file I/O error handling**:
- `04_merge_md.py:39-44`: Wrap file open/read/write with try-except, raise informative error if files missing or corrupted
- `03_translate_md.py`: Add error handling for file reads in translate loop (lines 554+)

**3c. Improve subprocess error messages**:
- `07_generate_formats.py:34-142`: Improve `translate_title_with_claude()` to use `GeminiProvider` instead of hardcoded CLI
- `07_generate_formats.py:369,394`: Remove duplicate imports of subprocess/glob

**3d. Add critical error handling tests**:
- `test_gemini_provider.py`: `test_translate_chunk_raises_on_nonzero_return_code()` — Verify CLI errors include stderr
- `test_translate_step3_refactor.py`: `test_select_model_with_fallback_all_unavailable_error_message()` — Verify error lists attempted chain
- `test_md_to_html_alternating.py`: `test_parse_alternating_segments_missing_marker()` — Malformed markdown handling
- `test_md_to_html_alternating.py`: `test_paragraphs_html_escapes_html_chars()` — XSS prevention

**Why**: Silent failures hide real issues. Users can't debug without error context.
**Verification**: pytest -q, ruff check

---

#### Commit 4: Add Comprehensive Type Annotations
**Files**: All pipeline scripts (`01_*.py`, `02_*.py`, `03_translate_md.py`, `04_merge_md.py`, `05_md_to_html.py`, `06_add_toc.py`, `07_generate_formats.py`)
**Changes**:

**Phase 1 (Priority)**: `03_translate_md.py` — annotate all ~40 functions
```python
def resolve_model_name(name: str, config: dict[str, Any]) -> str:
    """Resolve alias or return full model name."""
    ...

def translate_with_gemini_cli(chunk: str, prompt: str, model: str) -> str:
    """Translate markdown chunk with Gemini CLI."""
    ...
```

**Phase 2**: `04_merge_md.py`, `05_md_to_html.py`, `06_add_toc.py` — annotate all functions
**Phase 3**: `01_*.py`, `02_*.py`, `07_generate_formats.py` — annotate all functions

**Add `from __future__ import annotations`** at top of each file if not present.

**Why**: Global CLAUDE.md rule 5: "No Untyped Code. `any` is forbidden." Enables better IDE support and catches bugs at static analysis time.
**Verification**: ruff check, `py_compile` on modified files

---

#### Commit 5: Add Test Coverage for Error and Edge Cases
**Files**: `tests/unit/test_*.py`
**New Tests** (~15 total):

**Critical error handling tests (4)**:
1. `test_gemini_provider.py::test_translate_chunk_raises_on_nonzero_return_code` — Subprocess error propagation
2. `test_translate_step3_refactor.py::test_select_model_with_fallback_all_unavailable` — Error message includes attempted chain
3. `test_md_to_html_alternating.py::test_parse_alternating_segments_missing_marker` — Malformed markdown handling
4. `test_md_to_html_alternating.py::test_paragraphs_html_escapes_html_chars` — XSS prevention (security)

**Important tests (11)**:
- Markdown edge cases: empty sections, multiple markers, malformed separators (3 tests)
- Model selection boundaries and fallback configuration (3 tests)
- Config loading fallback paths and merging (2 tests)
- Quota tracker concurrent writes and date parameter (2 tests)
- File I/O error handling in merge step (1 test)

**Testing approach**: Test-first where possible (write failing test, fix code). Mock external dependencies (Gemini CLI, file system where appropriate).

**Why**: Tests prevent regression. Edge cases in markdown parsing and error handling directly impact user experience.
**Verification**: pytest -q (all 33 + 15 = 48 tests pass)

---

#### Commit 6: Update Documentation and Docstrings
**Files**: `CLAUDE.md`, `03_translate_md.py`, `04_merge_md.py`, `ai/gemini_provider.py`, `ai/model_probe.py`, `ai/bilingual_merger.py`, `ai/model_selector.py`, `07_generate_formats.py`
**Changes**:

**6a. Fix CLAUDE.md**:
- Line 36: Correct model selection sequence from "requested → alias → probe → fallback" to:
  ```
  1. Chunk size (if thresholds configured) → ModelSelector
  2. CLI --model parameter override
  3. Alias resolution
  4. Probe availability check
  5. Fallback chain
  ```

**6b. Add critical docstrings** (5 functions):
- `04_merge_md.py:25 merge_markdown_files()` — Step 4 entry point
- `ai/model_probe.py:64 probe()` — Cache behavior and TTL
- `ai/gemini_provider.py:15 translate_chunk()` — Error handling guarantees
- `ai/model_selector.py:36 select()` — Threshold algorithm
- `ai/bilingual_merger.py:5 merge()` — Output format and chunk ordering

**6c. Update comments**:
- `07_generate_formats.py`: Document that `translate_title_with_claude()` was migrated to Gemini or mark as deprecated

**Why**: Documentation drift causes confusion. Users and maintainers need to understand code behavior without reading implementation.
**Verification**: Manual review, no pytest impact

---

#### Commit 7: Tighten Ruff Configuration
**Files**: `pyproject.toml`
**Changes**:

**Line 20** — Remove `E722` from ignore list:
```toml
# Before:
ignore = ["E722", "F401", "F541", "F841", "I001"]

# After:
ignore = ["F401", "F541", "F841", "I001"]  # E722 removed
```

**Consider removing** (optional, but recommended):
- `F841` (unused variables) — Often indicates bugs

**Comment update**: Change "transitional baseline" to "focused baseline" and document what each ignore is for.

**Why**: E722 (bare except) directly conflicts with error handling improvements and "No Untyped Code" philosophy. Ruff should catch, not hide, issues.
**Verification**: ruff check (should now catch any remaining bare except: — but we already fixed them in Commit 3)

---

### Final Verification Gate

After all 7 commits, run dev verification suite:

```bash
uv run ruff check .              # No style violations
uv run ruff format --check .     # No formatting issues
uv run pytest -q                 # All 48 tests pass
bash -n translatebook.sh         # Script syntax valid
uv run python -m py_compile \
  03_translate_md.py \
  ai/gemini_provider.py \
  ai/model_probe.py \
  05_md_to_html.py \
  07_generate_formats.py          # All critical modules compile
```

---

## Work Breakdown

| Commit | Task | Est. Time |
|--------|------|-----------|
| 1 | Remove dead code | 15 min |
| 2 | pip → uv migration | 10 min |
| 3 | Error handling + 4 tests | 60 min |
| 4 | Type annotations (60 functions) | 90 min |
| 5 | 15 new tests (11 additional) | 75 min |
| 6 | Documentation + docstrings | 30 min |
| 7 | Ruff config tightening | 10 min |
| — | Final verification + polish | 20 min |
| **Total** | | **310 min (~5.5 hours)** |

---

## Success Criteria

✅ **Code Quality**: All 12 issues resolved
✅ **Test Coverage**: 48 tests pass (33 existing + 15 new), 100% of critical paths covered
✅ **Type Safety**: All pipeline functions have type annotations, no `any` types
✅ **Error Handling**: No bare `except:`, all file I/O wrapped, informative error messages
✅ **Documentation**: CLAUDE.md accurate, 5 critical docstrings added
✅ **Verification**: All dev verification commands pass
✅ **Git History**: 7 logical, independent, bisectable commits

---

## Approval

**Design approved by**: User
**Date**: 2026-03-16
**Next step**: Invoke `writing-plans` skill to create implementation plan with detailed task breakdown
