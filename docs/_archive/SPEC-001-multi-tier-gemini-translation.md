---
specId: SPEC-001
title: Multi-Tier Gemini Translation Engine with EPUB Bilingual Output
status: 📝 草案 (Draft)
priority: P1 - Core Feature
creationDate: 2026-03-16
lastUpdateDate: 2026-03-16
owner: Lei Peng (AI-Assisted)
relatedSpecs: []
tags:
  - gemini-api
  - translation
  - multi-tier
  - epub-bilingual
  - quota-tracking
  - dynamic-model-selection
---

# SPEC-001: Multi-Tier Gemini Translation Engine with EPUB Bilingual Output

## 1. Goal

> Replace Claude-only translation with **Gemini-based multi-tier system** that dynamically selects models (Pro/Flash/Lite) based on chunk size, tracks daily quota per model, and outputs EPUB books with alternating bilingual format (original → translation → original → ...) to maximize cost efficiency while maintaining translation quality.

## 2. Background

### Current State
- `claude_translater` project uses Claude CLI exclusively for translation
- Single model, no intelligent selection based on content complexity
- No quota tracking or cost optimization
- Output is monolingual (Chinese only)
- User runs high-complexity book through friend's Skills solution → requires 50+ interactions over multiple sessions → unacceptable friction

### Pain Points
1. **High cost**: Claude has higher per-token pricing than Gemini
2. **Wasted quota**: Pro users have high Gemini quota (TPM/RPM limits) not being utilized
3. **No optimization**: Same expensive model used for simple and complex chunks
4. **Single language**: Full Chinese translation loses ability to verify against source
5. **High friction**: Skills-based solution requires constant user interaction mid-translation

### Opportunity
- Gemini pricing is lower and free tier has generous quotas for Pro users
- Gemini has three tiers: Pro (high quality) / Flash (balanced) / Lite (fast, acceptable)
- Chunk size correlates with complexity: small chunks (<5K chars) work fine with Flash
- EPUB supports bilingual alternating format (paragraph → translation → paragraph → ...)
- Zero-interaction workflow enables batch processing large books overnight

### Related Context
- Tested with 159-chunk, 538KB book: no quota exhaustion with Flash
- Observed: Flash output quality acceptable for most chunks; Pro needed only for dense technical sections
- EPUB is target format for portability and reader compatibility

## 3. Design Decision

### Chosen Approach
**Multi-tier dynamic model selection + EPUB bilingual alternating format + SQLite quota tracking**

```
Chunk Size ← determine → Select Model (Flash/Pro/Lite)
         ↓
    Translate (Gemini CLI)
         ↓
    Track Usage (SQLite)
         ↓
    Merge Original + Translation
         ↓
    Format: Alternating bilingual (Markdown → HTML)
         ↓
    Generate: HTML → EPUB (pandoc)
```

### Model Selection Logic
```
If chunk_size < 5,000 chars:
    model = 'gemini-2.5-flash'
Elif chunk_size < 10,000 chars:
    model = config.model_thresholds[medium] or 'gemini-2.5-flash' (default)
Else:
    model = 'gemini-2.5-pro'
```

**First-time setup**: Run `--benchmark` on first book to empirically verify thresholds; save to `~/.config/translatebook/model_benchmarks.json`; subsequent books use saved thresholds.

### Rationale
| Alternative | Pros | Cons | Decision |
|-------------|------|------|----------|
| **Multi-tier Gemini** | Lower cost, high quota for Pro users, dynamic optimization, zero interaction | Requires quota tracking, testing framework | ✅ **Chosen** |
| Single Claude only | Proven, stable, simple | Expensive, ignores Gemini's 10x higher quota | ❌ |
| Skills-based approach | Advanced, leverages OpenClaw | 50+ interactions required, opaque, hard to debug | ❌ |
| Claude + Gemini hybrid | Maximum flexibility | Complexity, mixed quotas to track | ❌ Deferred to Phase 3 |

### Why EPUB Alternating Bilingual?
- EPUB readers (Calibre, Kindle, Apple Books) render alternating paragraphs naturally
- Preserves readability: readers can skip translations and read original if needed
- Easier to debug: compare side-by-side in readers without folder complexity
- Single-file distribution (no separate language versions)
- Markdown → HTML → EPUB conversion path already exists in codebase

## 4. Implementation Phases

### Phase 1: Gemini Provider + Dynamic Model Selection — Target: 2026-04-01
**Deliverable**: Functional 03_translate_md.py using Gemini CLI with dynamic model selection

Core modules (can develop in parallel):
- [ ] `ai/gemini_provider.py` — Gemini CLI adapter for three tiers (Pro/Flash/Lite)
- [ ] `ai/model_selector.py` — Chunk size → model selection logic
- [ ] `~/.config/translatebook/config.json` — Configuration template
- [ ] `03_translate_md.py` — Refactor to use GeminiProvider instead of Claude CLI

Acceptance:
- [ ] Gemini CLI called successfully for chunk translation
- [ ] Model selection respects size thresholds (testable with different chunk sizes)
- [ ] Configuration file read and CLI parameters override config
- [ ] Translation output matches expected format (same as current output_page*.md)

### Phase 2: Bilingual Merger + EPUB Output — Target: 2026-04-15
**Deliverable**: EPUB books with alternating bilingual format

Modules:
- [ ] `ai/bilingual_merger.py` — Interleave original chunks with translations
- [ ] `04_merge_md.py` — Updated to produce bilingual Markdown
- [ ] `05_md_to_html.py` — Transform to alternating HTML format
- [ ] `07_generate_formats.py` — Validate pandoc EPUB generation from bilingual HTML

Acceptance:
- [ ] EPUB file generated without pandoc errors
- [ ] EPUB renders correctly in Calibre/Apple Books (alternating paragraphs)
- [ ] Original and translated text both present and correct

### Phase 3: Quota Tracking + Benchmarking — Target: 2026-05-01
**Deliverable**: Auto-quota tracking and intelligent model selection based on empirical testing

Modules:
- [ ] `ai/quota_tracker.py` — SQLite schema + usage tracking
- [ ] `benchmark_models.py` — Test framework (sample 3-5 chunks, compare Flash vs Pro quality)
- [ ] `~/.config/translatebook/quota.db` — SQLite database auto-initialized
- [ ] `~/.config/translatebook/model_benchmarks.json` — Threshold recommendations auto-generated

Acceptance:
- [ ] Quota database stores model usage per day
- [ ] Automatic daily reset at UTC midnight
- [ ] Benchmark tool generates quality comparison matrix
- [ ] Model thresholds auto-saved and used in subsequent runs

### Phase 4: CLI Enhancement + Documentation — Target: 2026-05-15
**Deliverable**: Full CLI support and user-facing documentation

Modules:
- [ ] `translatebook.sh` — New parameters: `--model`, `--sample-only`, `--output-format`, `--benchmark`, `--quota-status`
- [ ] `CLAUDE.md` / `README.md` — Comprehensive usage guide for new features

Acceptance:
- [ ] `./translatebook.sh --help` lists all new parameters
- [ ] `./translatebook.sh --model pro book.pdf` and `--model gemini-2.5-pro` both work (alias + full model)
- [ ] `./translatebook.sh --benchmark book.pdf` generates thresholds
- [ ] Existing workflows (no parameters) still work (backward compatible)

## 5. Acceptance Criteria

Project is complete when:
- [ ] **Functional**: `./translatebook.sh --model flash book.pdf` (or full model name) produces EPUB with bilingual alternating format
- [ ] **Quality**: Flash-translated chunks at < 5K chars show acceptable quality (no manual post-edit needed)
- [ ] **Efficiency**: Pro-tier used only for chunks > 10K chars (verified by quota database)
- [ ] **Compatibility**: Generated EPUB renders correctly in Calibre, Apple Books, Kindle
- [ ] **Zero-friction**: Entire 200+ page book translates without user interaction
- [ ] **Testable**: 90%+ code coverage with unit tests for GeminiProvider, ModelSelector, BilingualMerger
- [ ] **Documented**: CLAUDE.md updated with usage examples, benchmarking workflow, quota interpretation

## 6. Implementation Notes

### Technology Choices
- **Gemini CLI**: Official `gemini` command-line tool (not REST API) — avoids additional auth complexity
- **SQLite**: Local quota tracking (avoid Prisma/ORM overhead for simple schema)
- **Bilingual Markdown internally**: Store original + translated chunks side-by-side, then format to HTML on output
- **TDD**: Write tests first for each module before implementation (see Test Plan below)

### Test-Driven Development Plan

#### Test Suite Structure
```
tests/
├── unit/
│   ├── test_gemini_provider.py        (GeminiProvider calls)
│   ├── test_model_selector.py         (Size → model mapping)
│   ├── test_bilingual_merger.py       (Interleaving logic)
│   ├── test_quota_tracker.py          (SQLite operations)
│   └── test_benchmark_models.py       (Quality comparison)
├── integration/
│   ├── test_translate_pipeline.py     (03_translate_md.py)
│   ├── test_merge_pipeline.py         (04_merge_md.py)
│   └── test_epub_generation.py        (07_generate_formats.py)
└── fixtures/
    ├── sample_chunks.md               (Test data)
    └── expected_bilingual_html.html   (Reference output)
```

#### Phase 1 Tests (Unit + Integration)
```python
# test_gemini_provider.py
def test_translate_chunk_with_flash_model():
    """GeminiProvider.translate_chunk calls gemini CLI with correct model."""
    provider = GeminiProvider(model='gemini-2.5-flash')
    result = provider.translate_chunk("English text", chunk_size=3000, system_prompt="...")
    assert isinstance(result, str)
    assert len(result) > 0  # Should return non-empty translation

def test_translate_with_pro_model():
    """Verify Pro model is selectable."""
    provider = GeminiProvider(model='gemini-2.5-pro')
    # [similar assertion]

# test_model_selector.py
def test_select_flash_for_small_chunks():
    """Chunks < 5000 chars → Flash."""
    selector = ModelSelector(config={'model_thresholds': {...}})
    assert selector.select(chunk_size=3000) == 'gemini-2.5-flash'

def test_select_pro_for_large_chunks():
    """Chunks > 10000 chars → Pro."""
    assert selector.select(chunk_size=15000) == 'gemini-2.5-pro'

# test_translate_md.py (integration)
def test_translate_md_respects_model_override():
    """CLI --model parameter overrides config file."""
    # Run: 03_translate_md.py --model gemini-2.5-pro chunk.md
    # Verify output_chunk.md is created and model was gemini-2.5-pro
```

#### Phase 2 Tests
```python
# test_bilingual_merger.py
def test_merge_original_and_translation():
    """BilingualMerger produces alternating format."""
    merger = BilingualMerger()
    result = merger.merge(
        original_chunks=['Hello world', 'Second paragraph'],
        translated_chunks=['你好世界', '第二段']
    )
    # Verify alternating: orig → trans → orig → trans
    assert 'Hello world' in result
    assert '你好世界' in result
    # Check order is correct

# test_epub_generation.py (integration)
def test_generate_epub_from_bilingual_html():
    """pandoc HTML → EPUB conversion works."""
    # Create test bilingual HTML file
    # Run: 07_generate_formats.py
    # Verify book.epub created and readable
    # Extract text from EPUB, verify both languages present
```

#### Phase 3 Tests
```python
# test_quota_tracker.py
def test_initialize_quota_db():
    """SQLite database created with correct schema."""
    tracker = QuotaTracker(db_path='test_quota.db')
    # Verify tables exist: quota_usage
    
def test_track_model_usage():
    """Record gemini-2.5-pro usage increment."""
    tracker.record_usage(model='gemini-2.5-pro', tier='pro', tokens=1000, date='2026-03-16')
    # Verify database entry

# test_benchmark_models.py
def test_benchmark_creates_json_output():
    """Benchmark tool samples chunks and compares models."""
    # Mock Gemini responses
    # Run benchmark with 3 test chunks
    # Verify model_benchmarks.json created with thresholds
```

### Testing Strategy
- **Unit tests**: Fast, no external dependencies (mock Gemini CLI)
- **Integration tests**: Use `pytest-subprocess` to mock CLI calls; verify file I/O
- **Fixtures**: Sample Markdown chunks, expected HTML/EPUB outputs
- **CI/CD**: GitHub Actions runs all tests on PR; blocks merge on failures

## 7. Fork vs. Branch Strategy

### Recommendation: **Create new directory** (not fork)

**Rationale**:
- Current `claude_translater` is single-repo, single-branch
- This is a **breaking change** (Claude → Gemini, output format changes)
- Users may want to keep Claude version working
- Cleaner to have separate projects than manage two major versions in one repo

**Proposal**:
```
/Users/leipeng/Documents/Projects/
├── claude_translater/          (legacy, keep as-is)
├── gemini_translater/          (NEW — start fresh)
│   ├── .git (new repo)
│   ├── docs/
│   │   └── architecture/
│   │       └── specs/SPEC-001-*.md
│   ├── tests/                  (TDD structure)
│   ├── ai/                      (new modules)
│   ├── 03_translate_md.py      (refactored)
│   ├── 04_merge_md.py          (refactored)
│   ├── 05_md_to_html.py        (refactored)
│   ├── 07_generate_formats.py  (unchanged)
│   ├── translatebook.sh        (enhanced)
│   └── README.md               (updated)
```

**Benefits**:
- ✅ Clean separation: legacy Claude path stays stable
- ✅ Independent git history: easier to bisect issues
- ✅ No breaking changes for users still using claude_translater
- ✅ Can publish gemini_translater as separate package later
- ✅ Testing setup in new repo won't interfere with existing code

**Migration Path**:
1. Build `gemini_translater` as independent project (Phase 1-4 above)
2. Once stable and tested, announce as "v2.0" replacement
3. Archive `claude_translater` with deprecation notice
4. Optional: Create `claude_translater → gemini_translater` migration guide

## 8. Status History

| Date | Status | Note |
|------|--------|------|
| 2026-03-16 | 📝 草案 (Draft) | Initial SPEC based on user requirements and brainstorming |

## 9. Related

- **Code**: `/Users/leipeng/Documents/Projects/BookWeaver/` (current)
- **Test Plan**: See Section 6 "Test-Driven Development Plan"
- **Related Project**: `/Users/leipeng/Documents/Projects/translate-book/` (Skills-based alternative, not recommended)


## Acknowledgements
This spec and design adapt ideas from the original Claude-based project: https://github.com/wizlijun/claude_translater. Thanks to the original author and contributors for the foundation.
