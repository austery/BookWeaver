"""Unit tests for EpubSourceAdapter.

Uses fake loaders and patchers — no real EPUB file I/O.
Tests the adapter's orchestration: segment ID generation, ordering,
grouping by document, and correct delegation to epub_package functions.
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai.adapters.sources.epub_adapter import EpubSourceAdapter, _resolve_spine_xhtml_paths
from ai.ports.source import TranslatedSegment


# ── Fake epub_package types ───────────────────────────────────


@dataclass(frozen=True)
class FakeManifestItem:
    id: str
    href: str
    media_type: str | None = "application/xhtml+xml"


@dataclass(frozen=True)
class FakeModel:
    epub_path: Path
    opf_path: str
    spine_itemrefs: list[str]
    manifest_items: dict[str, FakeManifestItem]
    cover_item_id: str | None = None
    toc_item_id: str | None = None


@dataclass(frozen=True)
class FakeRawSegment:
    text: str
    block_path: tuple[int, ...]
    tag_name: str


# ── Helpers ───────────────────────────────────────────────────


def _make_test_epub(doc_contents: dict[str, str], opf_path: str = "OEBPS/content.opf") -> Path:
    """Create a temporary EPUB zip file for adapter tests."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, content in doc_contents.items():
            zf.writestr(path, content)
    buf.seek(0)

    tmp = tempfile.NamedTemporaryFile(suffix=".epub", delete=False)
    tmp.write(buf.getvalue())
    tmp.close()
    return Path(tmp.name)


def _two_doc_model(epub_path: Path) -> FakeModel:
    """Model with 2 XHTML spine docs."""
    return FakeModel(
        epub_path=epub_path,
        opf_path="OEBPS/content.opf",
        spine_itemrefs=["ch1", "ch2"],
        manifest_items={
            "ch1": FakeManifestItem(id="ch1", href="chapter1.xhtml"),
            "ch2": FakeManifestItem(id="ch2", href="chapter2.xhtml"),
        },
    )


# ── Spine path resolution ────────────────────────────────────


class TestResolveSpinePaths:
    def test_resolves_to_full_paths(self) -> None:
        model = _two_doc_model(Path("/fake.epub"))
        paths = _resolve_spine_xhtml_paths(model)
        assert paths == ["OEBPS/chapter1.xhtml", "OEBPS/chapter2.xhtml"]

    def test_skips_non_xhtml(self) -> None:
        model = FakeModel(
            epub_path=Path("/fake.epub"),
            opf_path="OEBPS/content.opf",
            spine_itemrefs=["ch1", "img1"],
            manifest_items={
                "ch1": FakeManifestItem(id="ch1", href="chapter1.xhtml"),
                "img1": FakeManifestItem(id="img1", href="cover.png", media_type="image/png"),
            },
        )
        assert _resolve_spine_xhtml_paths(model) == ["OEBPS/chapter1.xhtml"]

    def test_skips_missing_manifest_entries(self) -> None:
        model = FakeModel(
            epub_path=Path("/fake.epub"),
            opf_path="OEBPS/content.opf",
            spine_itemrefs=["ch1", "missing"],
            manifest_items={
                "ch1": FakeManifestItem(id="ch1", href="chapter1.xhtml"),
            },
        )
        assert _resolve_spine_xhtml_paths(model) == ["OEBPS/chapter1.xhtml"]

    def test_accepts_both_xhtml_and_html_media_types(self) -> None:
        """Regression test: support EPUBs with text/html media type.

        Some EPUB publishers (e.g., The Economist) declare content files as
        text/html instead of application/xhtml+xml, even though they are
        valid XML. This is permitted by EPUB spec and common in modern EPUBs.
        """
        model = FakeModel(
            epub_path=Path("/fake.epub"),
            opf_path="OEBPS/content.opf",
            spine_itemrefs=["ch1_xhtml", "ch2_html", "img1"],
            manifest_items={
                "ch1_xhtml": FakeManifestItem(
                    id="ch1_xhtml", href="chapter1.xhtml", media_type="application/xhtml+xml"
                ),
                "ch2_html": FakeManifestItem(
                    id="ch2_html", href="chapter2.html", media_type="text/html"
                ),
                "img1": FakeManifestItem(id="img1", href="cover.png", media_type="image/png"),
            },
        )
        paths = _resolve_spine_xhtml_paths(model)
        assert paths == ["OEBPS/chapter1.xhtml", "OEBPS/chapter2.html"]
        assert len(paths) == 2


# ── get_segments ──────────────────────────────────────────────


class TestGetSegments:
    def test_returns_segments_with_stable_ids(self) -> None:
        epub_path = _make_test_epub(
            {
                "OEBPS/chapter1.xhtml": "<p>Hello</p>",
                "OEBPS/chapter2.xhtml": "<p>World</p>",
            }
        )

        def fake_extract(xhtml: str, document_path: str | None = None) -> list[FakeRawSegment]:
            if "Hello" in xhtml:
                return [FakeRawSegment("Hello", (0,), "p")]
            return [FakeRawSegment("World", (0,), "p")]

        adapter = EpubSourceAdapter(
            epub_path,
            _load_package=lambda _: _two_doc_model(epub_path),
            _extract_segments=fake_extract,
        )

        segments = adapter.get_segments()

        assert len(segments) == 2
        assert segments[0].id == "OEBPS/chapter1.xhtml::0"
        assert segments[0].text == "Hello"
        assert segments[1].id == "OEBPS/chapter2.xhtml::0"
        assert segments[1].text == "World"
        epub_path.unlink()

    def test_multiple_segments_per_document(self) -> None:
        epub_path = _make_test_epub(
            {
                "OEBPS/chapter1.xhtml": "<p>A</p><p>B</p>",
            }
        )
        model = FakeModel(
            epub_path=epub_path,
            opf_path="OEBPS/content.opf",
            spine_itemrefs=["ch1"],
            manifest_items={
                "ch1": FakeManifestItem(id="ch1", href="chapter1.xhtml"),
            },
        )

        adapter = EpubSourceAdapter(
            epub_path,
            _load_package=lambda _: model,
            _extract_segments=lambda _, document_path=None: [
                FakeRawSegment("A", (0,), "p"),
                FakeRawSegment("B", (1,), "p"),
            ],
        )

        segments = adapter.get_segments()

        assert len(segments) == 2
        assert segments[0].id == "OEBPS/chapter1.xhtml::0"
        assert segments[1].id == "OEBPS/chapter1.xhtml::1"
        assert segments[0].text == "A"
        assert segments[1].text == "B"
        epub_path.unlink()

    def test_metadata_includes_doc_path_and_tag(self) -> None:
        epub_path = _make_test_epub(
            {
                "OEBPS/chapter1.xhtml": "<p>Text</p>",
            }
        )
        model = FakeModel(
            epub_path=epub_path,
            opf_path="OEBPS/content.opf",
            spine_itemrefs=["ch1"],
            manifest_items={
                "ch1": FakeManifestItem(id="ch1", href="chapter1.xhtml"),
            },
        )

        adapter = EpubSourceAdapter(
            epub_path,
            _load_package=lambda _: model,
            _extract_segments=lambda _, document_path=None: [
                FakeRawSegment("Text", (0, 2), "blockquote"),
            ],
        )

        seg = adapter.get_segments()[0]
        assert seg.metadata["doc_path"] == "OEBPS/chapter1.xhtml"
        assert seg.metadata["tag_name"] == "blockquote"
        assert seg.metadata["index"] == 0
        epub_path.unlink()

    def test_empty_epub(self) -> None:
        epub_path = _make_test_epub({"OEBPS/chapter1.xhtml": ""})
        model = FakeModel(
            epub_path=epub_path,
            opf_path="OEBPS/content.opf",
            spine_itemrefs=["ch1"],
            manifest_items={
                "ch1": FakeManifestItem(id="ch1", href="chapter1.xhtml"),
            },
        )

        adapter = EpubSourceAdapter(
            epub_path,
            _load_package=lambda _: model,
            _extract_segments=lambda _, document_path=None: [],
        )

        assert adapter.get_segments() == []
        epub_path.unlink()

    def test_get_segments_passes_document_path_to_extractor(self) -> None:
        epub_path = _make_test_epub({"OEBPS/chapter1.xhtml": "<p>Hello</p>"})
        model = FakeModel(
            epub_path=epub_path,
            opf_path="OEBPS/content.opf",
            spine_itemrefs=["ch1"],
            manifest_items={
                "ch1": FakeManifestItem(id="ch1", href="chapter1.xhtml"),
            },
        )
        extract_calls: list[tuple[str, str | None]] = []

        def fake_extract(xhtml: str, document_path: str | None = None) -> list[FakeRawSegment]:
            extract_calls.append((xhtml, document_path))
            return [FakeRawSegment("Hello", (0,), "p")]

        adapter = EpubSourceAdapter(
            epub_path,
            _load_package=lambda _: model,
            _extract_segments=fake_extract,
        )

        segments = adapter.get_segments()

        assert len(segments) == 1
        assert extract_calls == [("<p>Hello</p>", "OEBPS/chapter1.xhtml")]
        epub_path.unlink()

    def test_get_segments_supports_legacy_single_argument_extractor(self) -> None:
        epub_path = _make_test_epub({"OEBPS/chapter1.xhtml": "<p>Hello</p>"})
        model = FakeModel(
            epub_path=epub_path,
            opf_path="OEBPS/content.opf",
            spine_itemrefs=["ch1"],
            manifest_items={
                "ch1": FakeManifestItem(id="ch1", href="chapter1.xhtml"),
            },
        )
        extract_calls: list[str] = []

        def fake_extract(xhtml: str) -> list[FakeRawSegment]:
            extract_calls.append(xhtml)
            return [FakeRawSegment("Hello", (0,), "p")]

        adapter = EpubSourceAdapter(
            epub_path,
            _load_package=lambda _: model,
            _extract_segments=fake_extract,
        )

        segments = adapter.get_segments()

        assert len(segments) == 1
        assert extract_calls == ["<p>Hello</p>"]
        epub_path.unlink()


# ── apply_translations ────────────────────────────────────────


class TestApplyTranslations:
    def test_groups_by_document_and_patches(self) -> None:
        epub_path = _make_test_epub(
            {
                "OEBPS/ch1.xhtml": "<p>A</p><p>B</p>",
                "OEBPS/ch2.xhtml": "<p>C</p>",
            }
        )
        model = FakeModel(
            epub_path=epub_path,
            opf_path="OEBPS/content.opf",
            spine_itemrefs=["ch1", "ch2"],
            manifest_items={
                "ch1": FakeManifestItem(id="ch1", href="ch1.xhtml"),
                "ch2": FakeManifestItem(id="ch2", href="ch2.xhtml"),
            },
        )

        patch_calls: list[tuple[str, list[str], str | None]] = []

        def fake_patch(
            xhtml: str,
            translations: list[str],
            *,
            document_path: str | None = None,
        ) -> str:
            patch_calls.append((xhtml, translations, document_path))
            return f"PATCHED({document_path})"

        adapter = EpubSourceAdapter(
            epub_path,
            _load_package=lambda _: model,
            _extract_segments=lambda xhtml, document_path=None: (
                [FakeRawSegment("A", (0,), "p"), FakeRawSegment("B", (1,), "p")]
                if "A" in xhtml
                else [FakeRawSegment("C", (0,), "p")]
            ),
            _patch_xhtml=fake_patch,
        )

        adapter.get_segments()
        adapter.apply_translations(
            [
                TranslatedSegment(id="OEBPS/ch1.xhtml::0", original="A", translated="甲"),
                TranslatedSegment(id="OEBPS/ch1.xhtml::1", original="B", translated="乙"),
                TranslatedSegment(id="OEBPS/ch2.xhtml::0", original="C", translated="丙"),
            ]
        )

        assert len(patch_calls) == 2
        (_, first_translations, first_doc_path), (_, second_translations, second_doc_path) = (
            patch_calls
        )
        assert first_translations == ["甲", "乙"]
        assert first_doc_path == "OEBPS/ch1.xhtml"
        assert second_translations == ["丙"]
        assert second_doc_path == "OEBPS/ch2.xhtml"
        epub_path.unlink()

    def test_translations_sorted_by_index(self) -> None:
        """Translations provided out of order are sorted correctly."""
        epub_path = _make_test_epub({"OEBPS/ch.xhtml": "<p>X</p><p>Y</p>"})
        model = FakeModel(
            epub_path=epub_path,
            opf_path="OEBPS/content.opf",
            spine_itemrefs=["ch"],
            manifest_items={
                "ch": FakeManifestItem(id="ch", href="ch.xhtml"),
            },
        )

        captured: list[list[str]] = []

        def fake_patch(
            xhtml: str, translations: list[str], *, document_path: str | None = None
        ) -> str:
            captured.append(translations)
            return "PATCHED"

        adapter = EpubSourceAdapter(
            epub_path,
            _load_package=lambda _: model,
            _extract_segments=lambda _, document_path=None: [
                FakeRawSegment("X", (0,), "p"),
                FakeRawSegment("Y", (1,), "p"),
            ],
            _patch_xhtml=fake_patch,
        )

        adapter.get_segments()
        # Provide translations in REVERSE order
        adapter.apply_translations(
            [
                TranslatedSegment(id="OEBPS/ch.xhtml::1", original="Y", translated="乙"),
                TranslatedSegment(id="OEBPS/ch.xhtml::0", original="X", translated="甲"),
            ]
        )

        assert captured[0] == ["甲", "乙"]  # sorted by index
        epub_path.unlink()


# ── save ──────────────────────────────────────────────────────


class TestSave:
    def test_calls_repack_with_overrides(self) -> None:
        epub_path = _make_test_epub({"OEBPS/ch.xhtml": "<p>Hi</p>"})
        model = FakeModel(
            epub_path=epub_path,
            opf_path="OEBPS/content.opf",
            spine_itemrefs=["ch"],
            manifest_items={
                "ch": FakeManifestItem(id="ch", href="ch.xhtml"),
            },
        )

        repack_calls: list[tuple[Any, ...]] = []

        adapter = EpubSourceAdapter(
            epub_path,
            _load_package=lambda _: model,
            _extract_segments=lambda _, document_path=None: [FakeRawSegment("Hi", (0,), "p")],
            _patch_xhtml=lambda xhtml, trans, **kw: "PATCHED",
            _repack_epub=lambda src, out, overrides: repack_calls.append((src, out, overrides)),
        )

        adapter.get_segments()
        adapter.apply_translations(
            [
                TranslatedSegment(id="OEBPS/ch.xhtml::0", original="Hi", translated="你好"),
            ]
        )
        output_path = Path("output.epub")
        adapter.save(str(output_path))

        assert len(repack_calls) == 1
        src, out, overrides = repack_calls[0]
        assert src == epub_path
        assert out == output_path
        assert "OEBPS/ch.xhtml" in overrides
        epub_path.unlink()
