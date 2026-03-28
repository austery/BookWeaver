---
specId: SPEC-010
title: Terminology Extraction and Translation Constraints System
status: ✅ 已完成 — Strategy A MVP
priority: P2 - Quality Enhancement
creationDate: 2026-03-26
lastUpdateDate: 2026-03-28
owner: Lei Peng (AI-Assisted)
relatedSpecs:
  - SPEC-002
  - SPEC-004
  - SPEC-006
tags:
  - terminology
  - translation-quality
  - glossary
  - context-optimization
  - a-b-testing
  - failure-driven-redesign
---

# SPEC-010: Terminology Extraction and Translation Constraints System

## 1. Goal

> Improve technical terminology translation consistency and accuracy by extracting critical domain-specific terms and injecting lightweight glossary constraints into translation prompts, **without** causing context dilution or attention dispersion.

## 2. Problem Statement

### 2.1 Context: SPEC-004 Failed Experiment

This SPEC is a **redesign informed by SPEC-004's A/B test failure**. 

**SPEC-004 background**:
- Attempted to implement baoyu-style orchestrated workflow
- Branch: `feature/spec004-agent-eval-wip` (worktree: `.worktrees/spec004-orchestrated-eval`)
- A/B test date: 2026-03-22
- Result: **Quality regression** — Dynamic orchestrated variant performed **worse** than baseline

**What SPEC-004 did wrong** (from `02-prompt.md` analysis):
- ❌ Injected 16 full-text paragraphs (~5000+ tokens) as "context"
- ❌ NO actual glossary or terminology constraints
- ❌ Vague instruction: "Keep proper nouns unchanged **when appropriate**"
- ❌ Result: "上下文稀释" (context dilution) — model attention scattered

**Evidence of failure**:
- Proper noun inconsistencies in Dynamic variant:
  - Antoninus: "安敦宁" vs "安东宁" (mixed in same chapter)
  - Fortuna: "福耳图娜" vs "福尔图娜"
  - Commodus: "康茂德" vs "科莫多斯"
- Baseline (no context) had **consistent** translations throughout
- Artifacts: `/Users/leipeng/Documents/Projects/BookWeaver/tmp/ab_first2_roman_emperor/`

**Key lesson**: Massive raw text injection degrades quality. This SPEC redesigns the approach with lightweight, structured glossaries.

See [SPEC-004](./SPEC-004-baoyu-agent-orchestrated-translation-evaluation.md) for complete A/B test analysis.

### 2.2 Current Pain Points

**Observed issues in translated books**:
- Technical terms mistranslated due to vocabulary confusion (e.g., "Connascence" → "并发性" instead of "共生性")
- Inconsistent terminology within the same book
- Reader comprehension severely impacted by incorrect key concept translations

**Previous failed attempt (spec004 worktree A/B test)**:
- ❌ Injected 16 full-text paragraphs (~5000+ tokens) as "context"
- ❌ No actual glossary or terminology constraints
- ❌ Result: **Worse** translation quality due to "context dilution" (上下文稀释)
- ❌ Proper nouns became inconsistent (Antoninus: "安敦宁" vs "安东宁")

**Root cause**: Massive raw text injection scattered model attention without providing explicit constraints.

### 2.2 Key Insight from Failure Analysis

**What worked** (Baseline without context):
- ✅ Consistent proper noun translation (model's default knowledge)
- ✅ Natural fluency
- ✅ Higher signal-to-noise ratio

**What failed** (Dynamic with massive context):
- ❌ Terminology inconsistency increased
- ❌ Model attention diluted across thousands of tokens
- ❌ Vague instructions ("when appropriate") provided no actionable constraints

### 2.3 Revised Understanding

**人名不需要约束** (Proper names don't need constraints):
- Models have trained memory of standard translations for historical figures
- Natural translation is consistent when not interfered with
- **Conclusion**: Exclude proper names from glossary

**专业术语必须约束** (Technical terms must be constrained):
- Author-invented concepts (e.g., "Connascence")
- Easily confused pairs (e.g., Connascence vs Concurrency)
- Domain-specific translations different from common usage
- **Conclusion**: Focus glossary on these critical terms only

## 3. Design Strategies

We propose **three strategy variants** for A/B testing, ordered by intervention level:

### Strategy A: Minimal Intervention (Recommended)

**Principle**: Extract only "易错" (error-prone) terminology. Let model handle the rest naturally.

**Extraction scope**:
- Index + TOC only (no full text needed)
- Extract 10-20 terms maximum
- Focus on:
  - Author-invented concepts
  - Easily confused term pairs (with negative constraints: "X ≠ Y")
  - Domain-specific jargon with non-obvious translations

**Glossary format**:
```json
{
  "critical_terminology": [
    {
      "term": "Connascence",
      "translation": "共生性",
      "negative_constraint": "NOT 并发性 (Concurrency)",
      "priority": "critical"
    },
    {
      "term": "Static Connascence",
      "translation": "静态共生性",
      "priority": "high"
    },
    {
      "term": "Shift Left",
      "translation": "向左移动",
      "context": "architectural practice",
      "priority": "medium"
    }
  ]
}
```

**Injection method**:
- Append to prompt as structured block (< 300 tokens)
- Use explicit language: "以下术语必须严格遵守标准译法"
- Include negative constraints for confusion-prone pairs

**Estimated cost**:
- Extraction: $0.05-0.10 per book (one-time, Index + TOC only)
- Translation overhead: +3-5% tokens per chapter

**Expected benefits**:
- High precision (only critical terms constrained)
- Low attention dilution risk
- Minimal token cost increase

---

### Strategy B: Moderate Coverage

**Principle**: Extract comprehensive terminology but curate to top 50 by priority.

**Extraction scope**:
- Index + TOC + Preface/Introduction
- Extract 30-50 terms
- Include:
  - All Strategy A categories
  - Recurring technical jargon (threshold: 3+ mentions in Index)
  - Key framework/methodology names

**Glossary format**:
```json
{
  "terminology": {
    "critical": [ /* Same as Strategy A */ ],
    "high_priority": [
      {
        "term": "Evolutionary Architecture",
        "translation": "演进式架构",
        "context": "book title concept"
      }
    ],
    "standard": [
      {
        "term": "Microservices",
        "translation": "微服务"
      }
    ]
  }
}
```

**Injection method**:
- Structured prompt block with priority tiers (< 600 tokens)
- Critical terms emphasized in prompt: "【核心术语】以下必须严格遵守"
- Standard terms as reference: "【参考术语】优先使用以下译法"

**Estimated cost**:
- Extraction: $0.10-0.20 per book
- Translation overhead: +8-12% tokens per chapter

**Expected benefits**:
- Better coverage of technical vocabulary
- Structured prioritization reduces attention dilution
- Balance between precision and recall

---

### Strategy C: Full Terminology Database (Research/Experimental)

**Principle**: Build comprehensive terminology database with domain classification.

**Extraction scope**:
- Index + TOC + Preface + First 2 Chapters
- Extract 50-100 terms with domain classification
- Include:
  - All technical terminology
  - Framework/tool names
  - Methodology concepts
  - Related work citations

**Glossary format**:
```json
{
  "metadata": {
    "book_domain": "software-architecture",
    "sub_domains": ["evolutionary-architecture", "microservices", "testing"]
  },
  "terminology_database": {
    "core_concepts": [ /* 10-15 critical terms */ ],
    "architectural_patterns": [ /* 15-20 terms */ ],
    "testing_practices": [ /* 10-15 terms */ ],
    "tools_frameworks": [ /* 10-15 terms */ ]
  }
}
```

**Injection method**:
- Conditional injection based on chapter content (requires chapter pre-analysis)
- Only inject relevant domain terms per chapter
- Token budget: < 800 tokens per chapter

**Estimated cost**:
- Extraction: $0.30-0.50 per book (multi-pass analysis)
- Translation overhead: +10-15% tokens per chapter (conditional injection reduces waste)

**Expected benefits**:
- Maximum terminology coverage
- Domain-aware injection reduces irrelevant terms
- Research baseline for quality ceiling

**Risks**:
- Higher complexity (requires chapter domain classification)
- Potential attention dilution if injection logic fails
- Higher token cost

---

## 4. Recommended Approach for Initial Implementation

**Start with Strategy A (Minimal Intervention)**

Rationale:
1. **Proven risk mitigation**: Avoids context dilution failure mode
2. **User alignment**: User observed baseline (no intervention) had better proper noun translation
3. **Cost efficiency**: Lowest token overhead
4. **Iterative validation**: Can expand to Strategy B if A proves insufficient

**A/B Test Plan**:
1. Implement Strategy A first
2. Test on 2-3 technical books with known terminology issues
3. Compare against current baseline (no glossary)
4. If quality improvement confirmed, implement Strategy B for comparison
5. Strategy C remains experimental research track

## 5. Implementation Plan

### Phase 1: Strategy A MVP (Target: 1-2 weeks)

**Prerequisites**:
- [ ] Define glossary JSON schema (`config/schemas/glossary_schema.json`)
- [ ] Add glossary configuration to `config/config.json`:
  ```json
  {
    "terminology_extraction": {
      "enabled": false,
      "strategy": "minimal",  // "minimal" | "moderate" | "comprehensive"
      "extraction_model": "gemini-2.5-pro",
      "max_terms": 20,
      "glossary_output_path": "{temp_dir}/extracted_glossary.json"
    }
  }
  ```

**Core implementation**:
- [ ] Create `00_extract_glossary.py` (new pipeline step)
  - Parse EPUB Index + TOC
  - Call extraction model with term limit
  - Validate output against schema
  - Write to `{temp_dir}/extracted_glossary.json`
- [ ] Modify `03_translate_md.py` or `ai/epub_translate_roundtrip.py`:
  - Load glossary if present
  - Inject into prompt template as `{GLOSSARY_BLOCK}`
  - Fallback to empty string if glossary disabled/missing
- [ ] Update `config/prompts/default_prompt.txt`:
  ```
  【关键术语约束】
  {GLOSSARY_BLOCK}
  
  以上术语必须严格遵守标准译法，确保全文一致性。
  ```
- [ ] Add CLI flag to `translatebook.sh`:
  ```bash
  --extract-glossary    # Enable terminology extraction before translation
  ```

**Testing**:
- [ ] Unit tests for glossary schema validation
- [ ] Unit tests for prompt injection logic
- [ ] Integration test: Extract from sample EPUB Index
- [ ] Integration test: Translate with glossary vs. without (A/B comparison)

**Documentation**:
- [ ] Update `README.md` with `--extract-glossary` usage
- [ ] Update `CLAUDE.md` with glossary injection behavior
- [ ] Add `docs/guides/terminology-extraction.md` user guide

### Phase 2: Strategy B Extension (Target: 2-3 weeks after Phase 1 validation)

**If Strategy A proves successful**:
- [ ] Expand extraction to include Preface
- [ ] Implement priority-based term filtering (top 50)
- [ ] Add structured glossary tiers (critical/high/standard)
- [ ] Update prompt template with tier-specific instructions

### Phase 3: Strategy C Research Track (Future, optional)

**If user requires maximum quality**:
- [ ] Implement chapter domain classification
- [ ] Build conditional injection logic
- [ ] Evaluate token cost vs. quality trade-off

## 6. Success Metrics

**Quality metrics** (manual evaluation on sample chapters):
- [ ] Critical terminology accuracy: Target 95%+ (vs. current unknown baseline)
- [ ] Terminology consistency: Same term → same translation across book
- [ ] No regression in proper noun translation (compare to current baseline)

**Cost metrics**:
- [ ] Token overhead: < 5% increase per chapter (Strategy A)
- [ ] Extraction cost: < $0.50 per book

**User experience**:
- [ ] Glossary extraction completes within 60 seconds
- [ ] No observable latency increase in translation step

## 7. Known Limitations & Risks

### Risk 1: Index Quality Dependency
- **Issue**: Not all EPUBs have comprehensive indexes
- **Mitigation**: Fallback to TOC-only extraction if Index missing
- **Acceptable failure mode**: Disable glossary extraction for books without Index/TOC

### Risk 2: False Negative Terms
- **Issue**: Some critical terms may not appear in Index
- **Mitigation**: Strategy B/C expand scope to Preface/Chapters
- **Acceptance**: Strategy A optimizes for precision over recall

### Risk 3: Over-Constraint
- **Issue**: Glossary might force unnatural translations in some contexts
- **Mitigation**: Use "优先使用" (prefer) rather than "必须使用" (must use) for standard terms
- **Testing**: A/B test to verify no fluency regression

### Risk 4: Model Hallucination in Extraction
- **Issue**: Model might invent false terminology or translations
- **Mitigation**: Use high-quality model (gemini-2.5-pro) for extraction
- **Future**: Optional human validation UI (out of scope for MVP)

## 8. Alternative Designs Considered

| Design | Pros | Cons | Decision |
|--------|------|------|----------|
| **A. Extract from full book text** | Maximum recall | 10-100x cost increase; context overload | ❌ Rejected |
| **B. Use external terminology databases** | No extraction cost | Domain coverage gaps; licensing issues | ❌ Rejected for MVP (could augment in future) |
| **C. Human-curated glossary** | Highest accuracy | Requires domain expertise; not scalable | ❌ Rejected (user lacks expertise) |
| **D. Post-translation terminology alignment** | No prompt injection needed | Requires NLP alignment; fragile for EPUB structure | ❌ Rejected (complexity) |
| **E. Lightweight Index extraction** | Low cost; high precision | Lower recall | ✅ Chosen as Strategy A |

## 9. A/B Test Protocol

### Test Setup
**Books for testing** (Select 2-3 technical books with known terminology issues):
- Book 1: "Building Evolutionary Architectures" (known issue: Connascence)
- Book 2: "Fundamentals of Software Architecture" (general technical terminology)
- Book 3: TBD (user selects based on recent translation issues)

**Test variants**:
- **Baseline**: Current pipeline (no glossary)
- **Variant A**: Strategy A (minimal intervention)
- **Variant B**: Strategy B (moderate coverage) — only if time permits

**Sample selection**:
- Chapter 1 + Chapter 4 (typically heavy in terminology)
- 3-5 pages per chapter
- Total ~6-10 pages per book

### Evaluation Criteria

**Primary metrics** (manual evaluation):
1. **Critical term accuracy**: Count mistranslations of Index-listed terms
2. **Consistency**: Same term should map to same translation (coefficient of variation)
3. **Fluency**: No unnatural phrasing (5-point Likert scale)
4. **Proper noun handling**: Verify no regression vs. baseline

**Secondary metrics** (automated):
1. Token overhead percentage
2. Translation time increase
3. Extraction time (Strategy A/B only)

**Decision criteria**:
- **Ship Variant A** if: Critical term accuracy improves by 20%+ AND no fluency regression
- **Iterate to Variant B** if: Variant A shows promise but recall too low
- **Revert to Baseline** if: Quality regression observed

## 10. Related Work & References

### Internal
- **spec004 worktree**: Failed A/B test with context dilution issue
  - Path: `/Users/leipeng/Documents/Projects/BookWeaver/tmp/ab_first2_roman_emperor/`
  - Lessons learned: No large text blocks; explicit constraints only
- **SPEC-002**: Prompt externalization (provides template injection mechanism)
- **SPEC-006**: EPUB translate roundtrip (integration point for glossary)

### External
- **baoyu-translate**: Reference architecture for glossary workflow
  - Path: `/Users/leipeng/Documents/Projects/baoyu-skills/skills/baoyu-translate/`
  - Differences: Markdown chunks vs. EPUB/XHTML; JavaScript vs. Python
- **Immersive Translate**: Public prompt profile patterns

### Research Context
- **Session analysis**: 2026-03-26 capacity exhaustion + terminology quality session
  - Artifact: `~/.copilot/session-state/.../files/terminology-extraction-design.md`
  - Key insight: Baseline (no intervention) beats over-injection

## 11. Future Enhancements (Out of Scope for MVP)

- [ ] User feedback loop: Mark incorrect translations → refine glossary
- [ ] Cross-book terminology database: Learn from previous translations
- [ ] Domain-specific terminology packs (architecture, ML, DevOps, etc.)
- [ ] Integration with external terminology APIs (e.g., Microsoft Terminology)
- [ ] Visual glossary review UI (web-based, optional)

## 12. Rollout Plan

**Step 1: Internal validation** (Week 1-2)
- Implement Strategy A
- Test on 2-3 books
- Iterate based on findings

**Step 2: Opt-in release** (Week 3)
- Document `--extract-glossary` flag
- Default: disabled (users must opt in)
- Collect user feedback

**Step 3: Refinement** (Week 4+)
- Evaluate Strategy B if needed
- Tune term count limits
- Consider default-on if quality consistently improves

**Step 4: Stabilization**
- Move `terminology_extraction.enabled` to `true` in default config
- Update all documentation
- Close SPEC as ✅ Completed

## 13. Open Questions

- [ ] Should glossary be cached across multiple books by same author?
- [ ] How to handle multi-volume series (share glossary or extract per book)?
- [ ] Should extraction model be same as translation model or always use Pro?
- [ ] CLI vs. API provider: Should CLI provider load glossary from file system directly?

## 14. Acceptance Criteria

### Strategy A MVP
- [x] Design document completed (this SPEC)
- [x] `00_extract_glossary.py` implemented and tested
- [x] `03_translate_md.py` or `ai/epub_translate_roundtrip.py` supports glossary injection
- [x] `translatebook.sh` exposes `--extract-glossary` flag
- [x] Unit tests: glossary schema, prompt injection, extraction logic
- [ ] Integration test: A/B comparison on 1 book shows improvement
- [x] Documentation: README, CLAUDE.md, user guide

### Strategy B Extension (Conditional on A success)
- [ ] Priority-based filtering implemented
- [ ] Structured tier injection tested
- [ ] A/B test confirms quality improvement vs. Strategy A

### Strategy C Research (Optional)
- [ ] Domain classification logic implemented
- [ ] Conditional injection tested
- [ ] Cost analysis documented

## 15. Appendix: Example Extraction Prompt

**Strategy A: Minimal Intervention Extraction Prompt**

```
你是技术书籍翻译专家。从以下EPUB的Index和目录中提取**容易翻译错误**的关键术语。

<INDEX>
{index_content}
</INDEX>

<TOC>
{toc_content}
</TOC>

提取要求：
1. **只提取专业术语和概念**（不要人名、地名、机构名）
2. **优先识别"易混淆"的术语对**（拼写相似但含义不同，如 Connascence vs Concurrency）
3. **标注作者原创的新概念**（本书首次提出的术语）
4. **最多20条术语**（聚焦最关键的术语）

输出JSON格式（严格遵守schema）：
{
  "critical_terminology": [
    {
      "term": "原文术语",
      "suggested_translation": "建议的中文翻译",
      "negative_constraint": "NOT 容易混淆的错误翻译",  // 可选
      "reason": "为什么这个术语容易翻译错误",
      "priority": "critical" | "high" | "medium"
    }
  ]
}

注意：
- 如果识别到易混淆术语对，必须在 negative_constraint 中明确指出错误翻译
- Priority分级标准：
  - critical: 作者原创概念 或 核心主题术语
  - high: 频繁出现的技术术语
  - medium: 重要但非核心的术语
```

---

**End of SPEC-010**
