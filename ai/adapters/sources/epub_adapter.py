"""EPUB source adapter — wraps ``epub_package`` for the hexagonal port.

Handles EPUB structure (spine ordering, XHTML extraction, bilingual
patching) internally.  The engine sees only flat ``Segment`` objects.
"""

from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path

from ai.ports.source import IBookSource, Segment, TranslatedSegment
from ai.epub_package import (
    EpubPackageModel,
    load_epub_package,
    extract_translatable_segments,
    patch_xhtml_alternating,
    repack_epub_with_overrides,
)


class EpubSourceAdapter(IBookSource):
    """Adapter wrapping ``epub_package`` functions for :class:`IBookSource`.

    All EPUB-specific structure (spine, manifest, XHTML DOM) is handled
    internally.  The engine only sees a flat list of ``Segment`` objects.

    """

    def __init__(self, epub_path: str | Path) -> None:
        self._epub_path = Path(epub_path)

        # Populated by get_segments()
        self._doc_order: list[str] = []
        self._doc_xhtml: dict[str, str] = {}
        self._overrides: dict[str, bytes] = {}
        self._loaded = False

    def get_segments(self) -> list[Segment]:
        """Extract segments from all spine XHTML documents."""
        self._ensure_loaded()

        result: list[Segment] = []
        for doc_path in self._doc_order:
            xhtml = self._doc_xhtml[doc_path]
            raw_segments = extract_translatable_segments(xhtml, document_path=doc_path)
            for i, seg in enumerate(raw_segments):
                result.append(
                    Segment(
                        id=f"{doc_path}::{i}",
                        text=seg.text,
                        metadata={
                            "doc_path": doc_path,
                            "index": i,
                            "tag_name": seg.tag_name,
                        },
                    )
                )

        return result

    def apply_translations(self, translated: list[TranslatedSegment]) -> None:
        """Patch each XHTML document with its translated segments."""
        by_doc: dict[str, list[tuple[int, str]]] = {}
        for ts in translated:
            doc_path, idx_str = ts.id.rsplit("::", 1)
            by_doc.setdefault(doc_path, []).append((int(idx_str), ts.translated))

        for doc_path, items in by_doc.items():
            items.sort(key=lambda x: x[0])
            translations = [text for _, text in items]
            patched = patch_xhtml_alternating(
                self._doc_xhtml[doc_path],
                translations,
                document_path=doc_path,
            )
            self._overrides[doc_path] = patched.encode("utf-8")

    def save(self, output_path: str) -> None:
        """Repack the EPUB with patched XHTML documents."""
        repack_epub_with_overrides(self._epub_path, Path(output_path), self._overrides)

    # ── Internal ──────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        model = load_epub_package(self._epub_path)
        self._doc_order = _resolve_spine_xhtml_paths(model)

        with zipfile.ZipFile(self._epub_path, "r") as zf:
            for doc_path in self._doc_order:
                self._doc_xhtml[doc_path] = zf.read(doc_path).decode("utf-8")

        self._loaded = True


def _resolve_spine_xhtml_paths(model: EpubPackageModel) -> list[str]:
    """Resolve spine itemrefs to XHTML/HTML zip paths.

    Accepts both 'application/xhtml+xml' and 'text/html' media types.
    Some EPUB publishers declare content files as text/html even when they are
    valid XML. This is permitted by the EPUB spec and common in modern EPUBs.
    """
    opf_dir = posixpath.dirname(model.opf_path)
    paths: list[str] = []
    for itemref in model.spine_itemrefs:
        item = model.manifest_items.get(itemref)
        if item is None:
            continue
        media = item.media_type
        # Accept both standard XHTML and HTML media types
        if media not in ("application/xhtml+xml", "text/html"):
            continue
        resolved = posixpath.normpath(posixpath.join(opf_dir, item.href))
        paths.append(resolved)
    return paths
