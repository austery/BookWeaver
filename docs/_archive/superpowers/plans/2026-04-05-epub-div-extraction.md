# EPUB `div` Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the EPUB workflow to translate prose-bearing `div` leaf blocks without regressing heading/TOC/container behavior or reusing stale checkpoints unsafely.

**Architecture:** Extend `ai.epub_package` from a narrow tag whitelist to a conservative leaf-block heuristic that includes `div` only when it behaves like prose. Add a checkpoint `segmenter_signature` in `ai.cli` so extraction-layout changes invalidate old EPUB checkpoints instead of silently misapplying cached translations.

**Tech Stack:** Python 3.13, `xml.etree.ElementTree`, pytest, Ruff, uv, git worktrees

---

## File Map

- Modify: `ai/epub_package.py:58-289`
  - Expand candidate block detection to include prose `div` nodes.
  - Add conservative `div` exclusion helpers for heading-like wrappers and structural containers.
- Modify: `ai/epub_package.py:518-563`
  - Reuse the updated extractor so `patch_xhtml_alternating()` can inject translations after qualified `div` nodes.
- Modify: `ai/cli.py:228-401`
  - Add `segmenter_signature` to checkpoint metadata, persistence, and compatibility checks.
- Modify: `tests/unit/test_epub_translate_patcher.py:69-302`
  - Add regression tests for `div` extraction, `div` patch injection, and conservative exclusions.
- Modify: `tests/unit/test_cli.py:1597-1736`
  - Add resume/checkpoint compatibility tests for the new `segmenter_signature`.

## Worktree

Implement in the already-created isolated worktree:

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver/.worktrees/epub-div-extraction
git branch --show-current
```

Expected:

```text
fix/epub-div-extraction
```

### Task 1: Extract prose-bearing `div` leaf blocks

**Files:**
- Modify: `tests/unit/test_epub_translate_patcher.py:69-118`
- Modify: `ai/epub_package.py:75-289, 518-563`
- Test: `tests/unit/test_epub_translate_patcher.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_extract_translatable_segments_includes_leaf_div_prose() -> None:
    from ai.epub_package import extract_translatable_segments

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<div class='calibre16'><span>When I graduated from law school in 1956.</span></div>"
        "</body></html>"
    )

    segments = extract_translatable_segments(source)

    assert len(segments) == 1
    assert segments[0].tag_name == "div"
    assert segments[0].text == "When I graduated from law school in 1956."


def test_extract_translatable_segments_skips_outer_div_when_inner_paragraph_exists() -> None:
    from ai.epub_package import extract_translatable_segments

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<div class='calibre16'><p>Inner paragraph.</p></div>"
        "</body></html>"
    )

    segments = extract_translatable_segments(source)

    assert [segment.tag_name for segment in segments] == ["p"]
    assert [segment.text for segment in segments] == ["Inner paragraph."]


def test_patch_xhtml_alternating_inserts_translation_after_prose_div() -> None:
    from ai.epub_package import patch_xhtml_alternating

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<div class='calibre16'><span>Leaf prose block.</span></div>"
        "</body></html>"
    )

    patched = patch_xhtml_alternating(source, ["叶子正文块。"])

    assert patched.count('class=\"bw-translation\"') == 1
    assert "Leaf prose block." in patched
    assert "叶子正文块。" in patched
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
uv run pytest -q \
  tests/unit/test_epub_translate_patcher.py::test_extract_translatable_segments_includes_leaf_div_prose \
  tests/unit/test_epub_translate_patcher.py::test_extract_translatable_segments_skips_outer_div_when_inner_paragraph_exists \
  tests/unit/test_epub_translate_patcher.py::test_patch_xhtml_alternating_inserts_translation_after_prose_div
```

Expected:

```text
FAILED tests/unit/test_epub_translate_patcher.py::test_extract_translatable_segments_includes_leaf_div_prose - assert 0 == 1
FAILED tests/unit/test_epub_translate_patcher.py::test_patch_xhtml_alternating_inserts_translation_after_prose_div - ValueError: translation count mismatch: expected 0, got 1
```

- [ ] **Step 3: Implement minimal `div` leaf extraction**

```python
_BLOCK_TAGS = {"p", "li", "blockquote", "dd", "div"}


def _normalize_visible_text(node: ET.Element) -> str:
    return " ".join("".join(node.itertext()).split())


def _has_translatable_block_descendant(node: ET.Element) -> bool:
    for descendant in node.iter():
        if descendant is node:
            continue
        tag = _local_name(descendant.tag).lower()
        if tag not in _BLOCK_TAGS:
            continue
        if _normalize_visible_text(descendant):
            return True
    return False


def _collect_translatable_block_segments(body: ET.Element) -> list[TranslatableSegment]:
    parent_map = _build_parent_map(body)
    segments: list[TranslatableSegment] = []
    for node in body.iter():
        tag_name = _local_name(node.tag).lower()
        if tag_name not in _BLOCK_TAGS:
            continue
        if _has_skip_ancestor(node, parent_map):
            continue
        if _is_heading_like_node(node):
            continue
        if _has_translatable_block_descendant(node):
            continue
        text = _normalize_visible_text(node)
        if not text:
            continue
        segments.append(
            TranslatableSegment(
                text=text,
                block_path=_node_path_from_body(body=body, node=node, parent_map=parent_map),
                tag_name=tag_name,
            )
        )
    return segments
```

- [ ] **Step 4: Run the targeted tests again and lint the touched files**

Run:

```bash
uv run pytest -q \
  tests/unit/test_epub_translate_patcher.py::test_extract_translatable_segments_includes_leaf_div_prose \
  tests/unit/test_epub_translate_patcher.py::test_extract_translatable_segments_skips_outer_div_when_inner_paragraph_exists \
  tests/unit/test_epub_translate_patcher.py::test_patch_xhtml_alternating_inserts_translation_after_prose_div && \
uv run ruff check ai/epub_package.py tests/unit/test_epub_translate_patcher.py
```

Expected:

```text
3 passed
All checks passed!
```

- [ ] **Step 5: Commit the green slice**

```bash
git add ai/epub_package.py tests/unit/test_epub_translate_patcher.py
git commit -m "fix: extract prose div blocks in EPUB" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Keep `div` handling conservative for headings and wrappers

**Files:**
- Modify: `tests/unit/test_epub_translate_patcher.py:69-302`
- Modify: `ai/epub_package.py:58-289`
- Test: `tests/unit/test_epub_translate_patcher.py`

- [ ] **Step 1: Write the failing exclusion tests**

```python
def test_extract_translatable_segments_skips_short_bold_heading_div() -> None:
    from ai.epub_package import extract_translatable_segments

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<div class='calibre13'><span class='bold'>CHAPTER 1</span></div>"
        "<div class='calibre16'><span>Body paragraph.</span></div>"
        "</body></html>"
    )

    segments = extract_translatable_segments(source)

    assert [segment.text for segment in segments] == ["Body paragraph."]


def test_extract_translatable_segments_skips_div_with_image_descendant() -> None:
    from ai.epub_package import extract_translatable_segments

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<div class='figure'><img src='cover.jpg' alt='cover'/><span>Cover</span></div>"
        "<div class='calibre16'><span>Real prose.</span></div>"
        "</body></html>"
    )

    segments = extract_translatable_segments(source)

    assert [segment.text for segment in segments] == ["Real prose."]
```

- [ ] **Step 2: Run the new exclusion tests to verify they fail**

Run:

```bash
uv run pytest -q \
  tests/unit/test_epub_translate_patcher.py::test_extract_translatable_segments_skips_short_bold_heading_div \
  tests/unit/test_epub_translate_patcher.py::test_extract_translatable_segments_skips_div_with_image_descendant
```

Expected:

```text
FAILED tests/unit/test_epub_translate_patcher.py::test_extract_translatable_segments_skips_short_bold_heading_div - assert ['CHAPTER 1', 'Body paragraph.'] == ['Body paragraph.']
FAILED tests/unit/test_epub_translate_patcher.py::test_extract_translatable_segments_skips_div_with_image_descendant - assert ['Cover', 'Real prose.'] == ['Real prose.']
```

- [ ] **Step 3: Implement conservative `div` exclusions**

```python
_STRUCTURAL_CONTAINER_TAGS = {
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "caption",
    "ul",
    "ol",
    "dl",
    "img",
    "svg",
    "nav",
}
_EMPHASIS_TAGS = {"b", "strong"}
_EMPHASIS_CLASS_HINTS = ("bold",)
_MAX_HEADING_LIKE_DIV_TEXT_LEN = 120


def _has_structural_container_descendant(node: ET.Element) -> bool:
    return any(
        descendant is not node and _local_name(descendant.tag).lower() in _STRUCTURAL_CONTAINER_TAGS
        for descendant in node.iter()
    )


def _has_emphasis_signal(node: ET.Element) -> bool:
    for descendant in node.iter():
        tag = _local_name(descendant.tag).lower()
        if tag in _EMPHASIS_TAGS:
            return True
        class_name = (descendant.get("class") or "").lower()
        if any(hint in class_name for hint in _EMPHASIS_CLASS_HINTS):
            return True
    return False


def _is_heading_like_node(node: ET.Element) -> bool:
    tag_name = _local_name(node.tag).lower()
    if tag_name in _HEADING_TAGS:
        return True

    class_name = (node.get("class") or "").lower()
    if any(hint in class_name for hint in _HEADING_CLASS_HINTS):
        return True

    if tag_name != "div":
        return False

    text = _normalize_visible_text(node)
    return bool(text) and len(text) <= _MAX_HEADING_LIKE_DIV_TEXT_LEN and _has_emphasis_signal(node)


def _collect_translatable_block_segments(body: ET.Element) -> list[TranslatableSegment]:
    parent_map = _build_parent_map(body)
    segments: list[TranslatableSegment] = []
    for node in body.iter():
        tag_name = _local_name(node.tag).lower()
        if tag_name not in _BLOCK_TAGS:
            continue
        if _has_skip_ancestor(node, parent_map):
            continue
        if _is_heading_like_node(node):
            continue
        if tag_name == "div" and _has_structural_container_descendant(node):
            continue
        if _has_translatable_block_descendant(node):
            continue
        text = _normalize_visible_text(node)
        if not text:
            continue
        segments.append(
            TranslatableSegment(
                text=text,
                block_path=_node_path_from_body(body=body, node=node, parent_map=parent_map),
                tag_name=tag_name,
            )
        )
    return segments
```

- [ ] **Step 4: Re-run new tests plus existing EPUB patcher regressions**

Run:

```bash
uv run pytest -q \
  tests/unit/test_epub_translate_patcher.py::test_extract_translatable_segments_skips_short_bold_heading_div \
  tests/unit/test_epub_translate_patcher.py::test_extract_translatable_segments_skips_div_with_image_descendant \
  tests/unit/test_epub_translate_patcher.py::test_patch_xhtml_alternating_skips_heading_translation \
  tests/unit/test_epub_translate_patcher.py::test_patch_xhtml_alternating_skips_toc_doc_translation \
  tests/unit/test_epub_translate_patcher.py::test_patch_xhtml_alternating_keeps_table_cells_source_only \
  tests/unit/test_epub_translate_patcher.py::test_patch_xhtml_alternating_preserves_ordered_list_item_count \
  tests/unit/test_epub_translate_patcher.py::test_patch_xhtml_alternating_preserves_unordered_list_item_count && \
uv run ruff check ai/epub_package.py tests/unit/test_epub_translate_patcher.py
```

Expected:

```text
7 passed
All checks passed!
```

- [ ] **Step 5: Commit the conservative-guard slice**

```bash
git add ai/epub_package.py tests/unit/test_epub_translate_patcher.py
git commit -m "fix: keep conservative div exclusions in EPUB" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Invalidate stale EPUB checkpoints when segment layout changes

**Files:**
- Modify: `tests/unit/test_cli.py:1613-1734`
- Modify: `ai/cli.py:228-401`
- Test: `tests/unit/test_cli.py`

- [ ] **Step 1: Write the failing checkpoint compatibility tests**

```python
def test_run_resume_rejects_checkpoint_when_segmenter_signature_missing(
    self,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _ResumeSource()
    provider = _ResumeProvider()
    self._patch_runtime_for_resume(monkeypatch, source, provider)

    in_epub = tmp_path / "book.epub"
    in_epub.write_bytes(b"epub")
    out_file = tmp_path / "out.epub"
    checkpoint_dir = tmp_path / "resume_cp_missing_signature"
    self._write_partial_checkpoint(
        checkpoint_dir=checkpoint_dir,
        input_epub=in_epub,
        segmenter_signature=None,
    )

    run(
        input_path=str(in_epub),
        output=str(out_file),
        input_format="epub",
        resume=True,
        checkpoint_dir=str(checkpoint_dir),
    )

    assert provider.calls == [["A", "B"], ["C"]]


def test_run_resume_rejects_checkpoint_when_segmenter_signature_mismatches(
    self,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _ResumeSource()
    provider = _ResumeProvider()
    self._patch_runtime_for_resume(monkeypatch, source, provider)

    in_epub = tmp_path / "book.epub"
    in_epub.write_bytes(b"epub")
    out_file = tmp_path / "out.epub"
    checkpoint_dir = tmp_path / "resume_cp_bad_signature"
    self._write_partial_checkpoint(
        checkpoint_dir=checkpoint_dir,
        input_epub=in_epub,
        segmenter_signature="epub-leaf-block-v1",
    )

    run(
        input_path=str(in_epub),
        output=str(out_file),
        input_format="epub",
        resume=True,
        checkpoint_dir=str(checkpoint_dir),
    )

    assert provider.calls == [["A", "B"], ["C"]]
```

- [ ] **Step 2: Run the targeted resume tests to verify they fail**

Run:

```bash
uv run pytest -q \
  tests/unit/test_cli.py::TestRunResumeCheckpoint::test_run_resume_rejects_checkpoint_when_segmenter_signature_missing \
  tests/unit/test_cli.py::TestRunResumeCheckpoint::test_run_resume_rejects_checkpoint_when_segmenter_signature_mismatches
```

Expected:

```text
FAILED tests/unit/test_cli.py::TestRunResumeCheckpoint::test_run_resume_rejects_checkpoint_when_segmenter_signature_missing - assert [['B'], ['C']] == [['A', 'B'], ['C']]
```

- [ ] **Step 3: Implement `segmenter_signature` in checkpoint metadata**

```python
_EPUB_SEGMENTER_SIGNATURE = "epub-leaf-block-v2"


@dataclass(frozen=True)
class CheckpointMetadata:
    input_signature: str
    input_format: str
    output_lang: str
    model: str
    provider: str
    max_batch_chars: int
    separator_overhead: int
    system_prompt_hash: str
    segmenter_signature: str | None


def _segmenter_signature_for_format(input_format: str) -> str | None:
    if input_format == "epub":
        return _EPUB_SEGMENTER_SIGNATURE
    return None


def _build_checkpoint_metadata(
    *,
    input_file: Path,
    input_format: str,
    output_lang: str,
    model: str,
    provider: str,
    max_batch_chars: int,
    separator_overhead: int,
    system_prompt: str,
) -> CheckpointMetadata:
    return CheckpointMetadata(
        input_signature=_compute_input_signature(input_file),
        input_format=input_format,
        output_lang=output_lang,
        model=model,
        provider=provider,
        max_batch_chars=max_batch_chars,
        separator_overhead=separator_overhead,
        system_prompt_hash=hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        segmenter_signature=_segmenter_signature_for_format(input_format),
    )


def _persist_checkpoint(
    *,
    checkpoint_dir: Path,
    metadata: CheckpointMetadata,
    translations: dict[str, str],
) -> None:
    state_payload: dict[str, object] = {
        "schema_version": _CHECKPOINT_SCHEMA_VERSION,
        "input_signature": metadata.input_signature,
        "input_format": metadata.input_format,
        "output_lang": metadata.output_lang,
        "model": metadata.model,
        "provider": metadata.provider,
        "max_batch_chars": metadata.max_batch_chars,
        "separator_overhead": metadata.separator_overhead,
        "system_prompt_hash": metadata.system_prompt_hash,
        "segmenter_signature": metadata.segmenter_signature,
        "translated_segment_count": len(translations),
    }


expected_pairs: tuple[tuple[str, str | int | None], ...] = (
    ("output_lang", metadata.output_lang),
    ("model", metadata.model),
    ("provider", metadata.provider),
    ("max_batch_chars", metadata.max_batch_chars),
    ("separator_overhead", metadata.separator_overhead),
    ("system_prompt_hash", metadata.system_prompt_hash),
    ("segmenter_signature", metadata.segmenter_signature),
)
```

Also update the checkpoint test helper so it can intentionally omit or override the field:

```python
def _write_partial_checkpoint(
    self,
    *,
    checkpoint_dir: Path,
    input_epub: Path,
    output_lang: str = "zh",
    model: str = "gemini-2.5-flash",
    segmenter_signature: str | None = "epub-leaf-block-v2",
) -> None:
    state = {
        "schema_version": 1,
        "input_signature": cli_module._compute_input_signature(input_epub),
        "input_format": "epub",
        "output_lang": output_lang,
        "model": model,
        "provider": "cli",
        "max_batch_chars": 60000,
        "separator_overhead": cli_module.SEPARATOR_OVERHEAD,
        "system_prompt_hash": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        "translated_segment_count": 1,
    }
    if segmenter_signature is not None:
        state["segmenter_signature"] = segmenter_signature
```

- [ ] **Step 4: Run the targeted CLI tests and format the touched files**

Run:

```bash
uv run pytest -q \
  tests/unit/test_cli.py::TestRunResumeCheckpoint::test_run_resume_skips_translated_segments_from_checkpoint \
  tests/unit/test_cli.py::TestRunResumeCheckpoint::test_run_force_resume_allows_model_mismatch_checkpoint \
  tests/unit/test_cli.py::TestRunResumeCheckpoint::test_run_resume_rejects_incompatible_checkpoint_without_force \
  tests/unit/test_cli.py::TestRunResumeCheckpoint::test_run_resume_rejects_checkpoint_when_segmenter_signature_missing \
  tests/unit/test_cli.py::TestRunResumeCheckpoint::test_run_resume_rejects_checkpoint_when_segmenter_signature_mismatches && \
uv run ruff format ai/cli.py tests/unit/test_cli.py && \
uv run ruff check ai/cli.py tests/unit/test_cli.py
```

Expected:

```text
5 passed
2 files reformatted
All checks passed!
```

- [ ] **Step 5: Commit the checkpoint-safety slice**

```bash
git add ai/cli.py tests/unit/test_cli.py
git commit -m "fix: invalidate stale EPUB checkpoints" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Run full verification in the worktree

**Files:**
- Verify: `ai/epub_package.py`
- Verify: `ai/cli.py`
- Verify: `tests/unit/test_epub_translate_patcher.py`
- Verify: `tests/unit/test_cli.py`

- [ ] **Step 1: Run the focused EPUB regression suite**

```bash
uv run pytest -q tests/unit/test_epub_translate_patcher.py tests/unit/test_cli.py
```

Expected:

```text
exit code 0 and no FAIL or ERROR lines in the pytest output
```

- [ ] **Step 2: Run repository-level verification**

```bash
uv run ruff check . && \
uv run ruff format --check . && \
uv run pytest -q && \
bash -n translatebook.sh
```

Expected:

```text
All checks passed!
451 passed, 1 skipped
```

- [ ] **Step 3: Confirm the diff stays scoped**

```bash
git --no-pager diff --stat main...HEAD
git --no-pager status --short
```

Expected:

```text
 ai/cli.py
 ai/epub_package.py
 tests/unit/test_cli.py
 tests/unit/test_epub_translate_patcher.py
```

- [ ] **Step 4: Capture the final branch summary for review**

```bash
git --no-pager log --oneline --decorate -5
```

Expected:

```text
fix: invalidate stale EPUB checkpoints
fix: keep conservative div exclusions in EPUB
fix: extract prose div blocks in EPUB
docs: add conservative EPUB div extraction design
```
