"""EPUB source adapter — wraps ``epub_package`` for the hexagonal port.

Handles EPUB structure (spine ordering, XHTML extraction, bilingual
patching) internally.  The engine sees only flat ``Segment`` objects.
"""

from __future__ import annotations

import posixpath
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai.ports.source import IBookSource, Segment, TranslatedSegment


@dataclass(frozen=True)
class _RawSegment:
    """Internal mirror of epub_package.TranslatableSegment."""

    text: str
    block_path: tuple[int, ...]
    tag_name: str


# ── Default operation loaders (import legacy at call time) ────


def _default_load_package(epub_path: Path) -> object:
    from ai.epub_package import load_epub_package

    return load_epub_package(epub_path)


def _default_extract_segments(xhtml: str) -> list[Any]:
    from ai.epub_package import extract_translatable_segments

    return extract_translatable_segments(xhtml)


def _default_patch_xhtml(
    xhtml: str,
    translations: list[str],
    *,
    document_path: str | None = None,
) -> str:
    from ai.epub_package import patch_xhtml_alternating

    return patch_xhtml_alternating(
        xhtml, translations, document_path=document_path
    )


def _default_repack(
    source: Path,
    output: Path,
    overrides: dict[str, bytes] | None = None,
) -> None:
    from ai.epub_package import repack_epub_with_overrides

    repack_epub_with_overrides(source, output, overrides)


# ── Adapter ───────────────────────────────────────────────────


class EpubSourceAdapter(IBookSource):
    """Adapter wrapping ``epub_package`` functions for :class:`IBookSource`.

    All EPUB-specific structure (spine, manifest, XHTML DOM) is handled
    internally.  The engine only sees a flat list of ``Segment`` objects.

    Args:
        epub_path: Path to the input EPUB file.
        _load_package: Injectable ``load_epub_package`` (for testing).
        _extract_segments: Injectable ``extract_translatable_segments``.
        _patch_xhtml: Injectable ``patch_xhtml_alternating``.
        _repack_epub: Injectable ``repack_epub_with_overrides``.
    """

    def __init__(
        self,
        epub_path: str | Path,
        *,
        _load_package: Callable[..., Any] | None = None,
        _extract_segments: Callable[..., list[Any]] | None = None,
        _patch_xhtml: Callable[..., str] | None = None,
        _repack_epub: Callable[..., None] | None = None,
    ) -> None:
        self._epub_path = Path(epub_path)
        self._load_fn = _load_package or _default_load_package
        self._extract_fn = _extract_segments or _default_extract_segments
        self._patch_fn = _patch_xhtml or _default_patch_xhtml
        self._repack_fn = _repack_epub or _default_repack

        # Populated by get_segments()
        self._doc_order: list[str] = []
        self._doc_xhtml: dict[str, str] = {}
        self._doc_raw_segments: dict[str, list[_RawSegment]] = {}
        self._overrides: dict[str, bytes] = {}
        self._loaded = False

    def get_segments(self) -> list[Segment]:
        """Extract segments from all spine XHTML documents."""
        self._ensure_loaded()

        result: list[Segment] = []
        for doc_path in self._doc_order:
            xhtml = self._doc_xhtml[doc_path]
            raw_segments = self._extract_fn(xhtml)

            coerced: list[_RawSegment] = []
            for i, raw in enumerate(raw_segments):
                seg = _RawSegment(
                    text=raw.text,
                    block_path=tuple(raw.block_path),
                    tag_name=raw.tag_name,
                )
                coerced.append(seg)
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
            self._doc_raw_segments[doc_path] = coerced

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
            patched = self._patch_fn(
                self._doc_xhtml[doc_path],
                translations,
                document_path=doc_path,
            )
            self._overrides[doc_path] = patched.encode("utf-8")

    def save(self, output_path: str) -> None:
        """Repack the EPUB with patched XHTML documents."""
        self._repack_fn(
            self._epub_path, Path(output_path), self._overrides
        )

    # ── Internal ──────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        model = self._load_fn(self._epub_path)
        self._doc_order = _resolve_spine_xhtml_paths(model)

        with zipfile.ZipFile(self._epub_path, "r") as zf:
            for doc_path in self._doc_order:
                self._doc_xhtml[doc_path] = zf.read(doc_path).decode("utf-8")

        self._loaded = True


def _resolve_spine_xhtml_paths(model: object) -> list[str]:
    """Resolve spine itemrefs to XHTML zip paths."""
    opf_dir = posixpath.dirname(model.opf_path)
    paths: list[str] = []
    for itemref in model.spine_itemrefs:
        item = model.manifest_items.get(itemref)
        if item is None:
            continue
        media = getattr(item, "media_type", None)
        if media != "application/xhtml+xml":
            continue
        resolved = posixpath.normpath(posixpath.join(opf_dir, item.href))
        paths.append(resolved)
    return paths
