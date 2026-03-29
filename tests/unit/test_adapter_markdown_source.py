"""Unit tests for MarkdownSourceAdapter.

Uses real temp directories with page*.md files — no mocking of the
filesystem.  The BilingualMerger is injected via ``_merge_fn`` to
keep tests isolated from the legacy module.
"""

from __future__ import annotations

from pathlib import Path

from ai.adapters.sources.markdown_adapter import MarkdownSourceAdapter
from ai.ports.source import TranslatedSegment


# ── Helpers ───────────────────────────────────────────────────


def _write_pages(directory: Path, pages: dict[str, str]) -> None:
    """Write filename→content pairs into *directory*."""
    for name, content in pages.items():
        (directory / name).write_text(content, encoding="utf-8")


# ── get_segments ──────────────────────────────────────────────


class TestGetSegments:
    def test_single_page(self, tmp_path: Path) -> None:
        _write_pages(tmp_path, {"page0001.md": "Hello world"})
        adapter = MarkdownSourceAdapter(tmp_path)
        segments = adapter.get_segments()

        assert len(segments) == 1
        assert segments[0].id == "page0001"
        assert segments[0].text == "Hello world"
        assert segments[0].metadata["filename"] == "page0001.md"
        assert segments[0].metadata["path"] == str(tmp_path / "page0001.md")

    def test_multiple_pages_sorted_naturally(self, tmp_path: Path) -> None:
        _write_pages(
            tmp_path,
            {
                "page0010.md": "Page ten",
                "page0001.md": "Page one",
                "page0002.md": "Page two",
            },
        )
        adapter = MarkdownSourceAdapter(tmp_path)
        segments = adapter.get_segments()

        assert len(segments) == 3
        assert [s.id for s in segments] == ["page0001", "page0002", "page0010"]
        assert [s.text for s in segments] == ["Page one", "Page two", "Page ten"]

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
        assert [s.id for s in segments] == ["page0001", "page0002"]

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
                TranslatedSegment(id="page0001", original="Hello", translated="你好"),
                TranslatedSegment(id="page0002", original="World", translated="世界"),
            ]
        )

        assert adapter._translations["page0001"] == "你好"
        assert adapter._translations["page0002"] == "世界"

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
        # Apply in reverse order
        adapter.apply_translations(
            [
                TranslatedSegment(id="page0003", original="Third", translated="第三"),
                TranslatedSegment(id="page0001", original="First", translated="第一"),
                TranslatedSegment(id="page0002", original="Second", translated="第二"),
            ]
        )

        assert adapter._translations["page0001"] == "第一"
        assert adapter._translations["page0002"] == "第二"
        assert adapter._translations["page0003"] == "第三"


# ── save ──────────────────────────────────────────────────────


class TestSave:
    def test_produces_bilingual_markdown(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        _write_pages(
            src_dir,
            {
                "page0001.md": "Hello",
                "page0002.md": "World",
            },
        )

        merge_calls: list[tuple[list[str], list[str]]] = []

        def fake_merge(originals: list[str], translations: list[str]) -> str:
            merge_calls.append((originals, translations))
            blocks: list[str] = []
            for i, (o, t) in enumerate(zip(originals, translations), start=1):
                blocks.append(f"## Segment {i}\n\n{o}\n\n**中文译文**\n\n{t}\n\n---\n\n")
            return "".join(blocks).strip() + "\n"

        adapter = MarkdownSourceAdapter(src_dir, _merge_fn=fake_merge)
        adapter.get_segments()
        adapter.apply_translations(
            [
                TranslatedSegment(id="page0001", original="Hello", translated="你好"),
                TranslatedSegment(id="page0002", original="World", translated="世界"),
            ]
        )

        output_file = tmp_path / "output.md"
        adapter.save(str(output_file))

        content = output_file.read_text(encoding="utf-8")
        assert "## Segment 1" in content
        assert "## Segment 2" in content
        assert "**中文译文**" in content
        assert "你好" in content
        assert "世界" in content

        # Verify merge was called with correct args
        assert len(merge_calls) == 1
        assert merge_calls[0][0] == ["Hello", "World"]
        assert merge_calls[0][1] == ["你好", "世界"]

    def test_save_preserves_page_ordering(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        _write_pages(
            src_dir,
            {
                "page0010.md": "Tenth",
                "page0001.md": "First",
            },
        )

        captured_originals: list[list[str]] = []

        def fake_merge(originals: list[str], translations: list[str]) -> str:
            captured_originals.append(list(originals))
            return "merged\n"

        adapter = MarkdownSourceAdapter(src_dir, _merge_fn=fake_merge)
        adapter.get_segments()
        adapter.apply_translations(
            [
                TranslatedSegment(id="page0001", original="First", translated="第一"),
                TranslatedSegment(id="page0010", original="Tenth", translated="第十"),
            ]
        )

        output_file = tmp_path / "output.md"
        adapter.save(str(output_file))

        # page0001 content must come before page0010
        assert captured_originals[0] == ["First", "Tenth"]
