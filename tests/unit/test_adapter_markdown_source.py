"""Unit tests for MarkdownSourceAdapter.

Uses real temp directories with page*.md files — no mocking of the
filesystem.  The BilingualMerger is injected via ``_merge_fn`` to
keep tests isolated from the legacy module.
"""

from __future__ import annotations

from pathlib import Path

from ai.adapters.sources.markdown_adapter import (
    MarkdownSourceAdapter,
    _is_fenced_code_block,
    _render_clean_bilingual,
    _split_blocks,
)
from ai.ports.source import TranslatedSegment


# ── Helpers ───────────────────────────────────────────────────


def _write_pages(directory: Path, pages: dict[str, str]) -> None:
    """Write filename→content pairs into *directory*."""
    for name, content in pages.items():
        (directory / name).write_text(content, encoding="utf-8")


# ── _split_blocks ─────────────────────────────────────────────


class TestSplitBlocks:
    def test_single_paragraph(self) -> None:
        assert _split_blocks("Hello world") == ["Hello world"]

    def test_two_paragraphs(self) -> None:
        text = "First paragraph.\n\nSecond paragraph."
        assert _split_blocks(text) == ["First paragraph.", "Second paragraph."]

    def test_heading_and_paragraph(self) -> None:
        text = "# Title\n\nSome body text."
        blocks = _split_blocks(text)
        assert blocks == ["# Title", "Some body text."]

    def test_fenced_code_block_kept_atomic(self) -> None:
        text = "Before.\n\n```python\ndef foo():\n    pass\n```\n\nAfter."
        blocks = _split_blocks(text)
        assert len(blocks) == 3
        assert blocks[0] == "Before."
        assert "def foo():" in blocks[1]
        assert "```" in blocks[1]
        assert blocks[2] == "After."

    def test_blank_lines_inside_fence_preserved(self) -> None:
        text = "```\nline1\n\nline2\n```"
        blocks = _split_blocks(text)
        assert len(blocks) == 1
        assert "line1\n\nline2" in blocks[0]

    def test_empty_text(self) -> None:
        assert _split_blocks("") == []
        assert _split_blocks("\n\n\n") == []

    def test_list_block(self) -> None:
        text = "# Title\n\n1. First\n2. Second\n   * Sub-item"
        blocks = _split_blocks(text)
        assert len(blocks) == 2
        assert blocks[0] == "# Title"
        assert "1. First" in blocks[1]
        assert "Sub-item" in blocks[1]


class TestRenderHelpers:
    def test_is_fenced_code_block_true(self) -> None:
        text = "```python\ndef foo():\n    return 1\n```"
        assert _is_fenced_code_block(text) is True

    def test_is_fenced_code_block_false(self) -> None:
        assert _is_fenced_code_block("normal paragraph") is False

    def test_render_clean_bilingual_no_meta_labels(self, tmp_path: Path) -> None:
        _write_pages(tmp_path, {"page0001.md": "# Title\n\nParagraph."})
        adapter = MarkdownSourceAdapter(tmp_path)
        segments = adapter.get_segments()
        adapter.apply_translations(
            [
                TranslatedSegment(
                    id=segments[0].id, original=segments[0].text, translated="# 标题"
                ),
                TranslatedSegment(
                    id=segments[1].id, original=segments[1].text, translated="段落。"
                ),
            ]
        )
        content = _render_clean_bilingual(segments, adapter._translations)
        assert "## Segment" not in content
        assert "**中文译文**" not in content
        assert "\n---\n" not in content
        assert content.startswith("# Title\n\n# 标题")

    def test_render_clean_bilingual_skips_duplicate_code_block(self, tmp_path: Path) -> None:
        _write_pages(tmp_path, {"page0001.md": "```python\nprint('x')\n```"})
        adapter = MarkdownSourceAdapter(tmp_path)
        segments = adapter.get_segments()
        adapter.apply_translations(
            [
                TranslatedSegment(
                    id=segments[0].id,
                    original=segments[0].text,
                    translated=segments[0].text,
                )
            ]
        )
        content = _render_clean_bilingual(segments, adapter._translations)
        assert content.count("```python") == 1

    def test_render_clean_bilingual_skips_duplicate_identical_non_code(
        self, tmp_path: Path
    ) -> None:
        _write_pages(tmp_path, {"page0001.md": "No change line."})
        adapter = MarkdownSourceAdapter(tmp_path)
        segments = adapter.get_segments()
        adapter.apply_translations(
            [
                TranslatedSegment(
                    id=segments[0].id,
                    original=segments[0].text,
                    translated=segments[0].text,
                )
            ]
        )
        content = _render_clean_bilingual(segments, adapter._translations)
        assert content.count("No change line.") == 1

    def test_render_clean_bilingual_code_block_changed_still_single_copy(
        self, tmp_path: Path
    ) -> None:
        original = "```python\n# original comment\nprint('x')\n```"
        translated = "```python\n# 已翻译注释\nprint('x')\n```"
        _write_pages(tmp_path, {"page0001.md": original})
        adapter = MarkdownSourceAdapter(tmp_path)
        segments = adapter.get_segments()
        adapter.apply_translations(
            [
                TranslatedSegment(
                    id=segments[0].id,
                    original=segments[0].text,
                    translated=translated,
                )
            ]
        )
        content = _render_clean_bilingual(segments, adapter._translations)
        assert content.count("```python") == 1
        assert "# 已翻译注释" in content
        assert "# original comment" not in content


# ── get_segments ──────────────────────────────────────────────


class TestGetSegments:
    def test_single_page_multiple_blocks(self, tmp_path: Path) -> None:
        _write_pages(tmp_path, {"page0001.md": "# Title\n\nParagraph one.\n\nParagraph two."})
        adapter = MarkdownSourceAdapter(tmp_path)
        segments = adapter.get_segments()

        assert len(segments) == 3
        assert segments[0].id == "page0001::0"
        assert segments[0].text == "# Title"
        assert segments[1].id == "page0001::1"
        assert segments[1].text == "Paragraph one."
        assert segments[2].id == "page0001::2"
        assert segments[2].text == "Paragraph two."
        assert segments[0].metadata["filename"] == "page0001.md"
        assert segments[0].metadata["block_index"] == 0

    def test_multiple_pages_sorted_naturally(self, tmp_path: Path) -> None:
        _write_pages(
            tmp_path,
            {
                "page0010.md": "Page ten",
                "page0001.md": "# One\n\nBody one",
                "page0002.md": "Page two",
            },
        )
        adapter = MarkdownSourceAdapter(tmp_path)
        segments = adapter.get_segments()

        # page0001 has 2 blocks, page0002 has 1, page0010 has 1
        assert len(segments) == 4
        assert segments[0].id == "page0001::0"
        assert segments[0].text == "# One"
        assert segments[1].id == "page0001::1"
        assert segments[1].text == "Body one"
        assert segments[2].id == "page0002::0"
        assert segments[3].id == "page0010::0"

    def test_filters_non_page_files(self, tmp_path: Path) -> None:
        _write_pages(
            tmp_path,
            {
                "page0001.md": "Real page",
                "output_page0001.md": "Should be ignored",
                "config.txt": "Also ignored",
                "page0002.md": "Another real page",
                "notes.md": "Not a page file",
            },
        )
        adapter = MarkdownSourceAdapter(tmp_path)
        segments = adapter.get_segments()

        assert len(segments) == 2
        ids = [s.id for s in segments]
        assert "page0001::0" in ids
        assert "page0002::0" in ids

    def test_empty_directory(self, tmp_path: Path) -> None:
        adapter = MarkdownSourceAdapter(tmp_path)
        segments = adapter.get_segments()
        assert segments == []


# ── apply_translations ────────────────────────────────────────


class TestApplyTranslations:
    def test_translations_stored_correctly(self, tmp_path: Path) -> None:
        _write_pages(
            tmp_path,
            {
                "page0001.md": "Hello",
                "page0002.md": "World",
            },
        )
        adapter = MarkdownSourceAdapter(tmp_path)
        adapter.get_segments()
        adapter.apply_translations(
            [
                TranslatedSegment(id="page0001::0", original="Hello", translated="你好"),
                TranslatedSegment(id="page0002::0", original="World", translated="世界"),
            ]
        )

        assert adapter._translations["page0001::0"] == "你好"
        assert adapter._translations["page0002::0"] == "世界"

    def test_out_of_order_translations(self, tmp_path: Path) -> None:
        _write_pages(
            tmp_path,
            {
                "page0001.md": "First",
                "page0002.md": "Second",
                "page0003.md": "Third",
            },
        )
        adapter = MarkdownSourceAdapter(tmp_path)
        adapter.get_segments()
        adapter.apply_translations(
            [
                TranslatedSegment(id="page0003::0", original="Third", translated="第三"),
                TranslatedSegment(id="page0001::0", original="First", translated="第一"),
                TranslatedSegment(id="page0002::0", original="Second", translated="第二"),
            ]
        )

        assert adapter._translations["page0001::0"] == "第一"
        assert adapter._translations["page0002::0"] == "第二"
        assert adapter._translations["page0003::0"] == "第三"


# ── save ──────────────────────────────────────────────────────


class TestSave:
    def test_produces_clean_alternating_bilingual_markdown(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        _write_pages(
            src_dir,
            {"page0001.md": "# Title\n\nHello world"},
        )
        adapter = MarkdownSourceAdapter(src_dir)
        adapter.get_segments()
        adapter.apply_translations(
            [
                TranslatedSegment(id="page0001::0", original="# Title", translated="# 标题"),
                TranslatedSegment(id="page0001::1", original="Hello world", translated="你好世界"),
            ]
        )

        output_file = tmp_path / "output.md"
        adapter.save(str(output_file))

        content = output_file.read_text(encoding="utf-8")
        assert "## Segment" not in content
        assert "**中文译文**" not in content
        assert "\n---\n" not in content
        assert "# Title" in content
        assert "# 标题" in content
        assert "你好世界" in content
        assert content.startswith("# Title\n\n# 标题")
        assert "\n\nHello world\n\n你好世界\n" in content

    def test_save_does_not_duplicate_unchanged_code_block(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        _write_pages(src_dir, {"page0001.md": "```python\nprint('x')\n```"})

        adapter = MarkdownSourceAdapter(src_dir)
        segs = adapter.get_segments()
        adapter.apply_translations(
            [
                TranslatedSegment(
                    id=segs[0].id,
                    original=segs[0].text,
                    translated=segs[0].text,
                )
            ]
        )

        output_file = tmp_path / "output.md"
        adapter.save(str(output_file))

        content = output_file.read_text(encoding="utf-8")
        assert content.count("```python") == 1

    def test_save_preserves_page_ordering(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        _write_pages(
            src_dir,
            {
                "page0010.md": "Tenth",
                "page0001.md": "# First\n\nBody",
            },
        )

        adapter = MarkdownSourceAdapter(src_dir)
        adapter.get_segments()
        adapter.apply_translations(
            [
                TranslatedSegment(id="page0001::0", original="# First", translated="# 第一"),
                TranslatedSegment(id="page0001::1", original="Body", translated="正文"),
                TranslatedSegment(id="page0010::0", original="Tenth", translated="第十"),
            ]
        )

        output_file = tmp_path / "output.md"
        adapter.save(str(output_file))
        content = output_file.read_text(encoding="utf-8")
        assert content.find("# First") < content.find("Tenth")
