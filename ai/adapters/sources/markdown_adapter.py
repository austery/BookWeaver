"""Markdown source adapter — reads split ``page*.md`` directories.

Handles the split-Markdown format produced by ``02_split_to_md.py``.
The engine sees only flat ``Segment`` objects; page ordering and
bilingual merging are handled internally.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from ai.ports.source import IBookSource, Segment, TranslatedSegment

_PAGE_RE = re.compile(r"^page\d+\.md$")


class MarkdownSourceAdapter(IBookSource):
    """Adapter for split-Markdown directories (``page*.md`` files).

    Args:
        markdown_dir: Directory containing ``page*.md`` files.
        _merge_fn: Injectable merge callable (for testing).  Defaults
            to ``BilingualMerger().merge`` loaded lazily.
    """

    def __init__(
        self,
        markdown_dir: str | Path,
        *,
        _merge_fn: Callable[[list[str], list[str]], str] | None = None,
    ) -> None:
        self._dir = Path(markdown_dir)
        self._merge_fn = _merge_fn

        self._segments: list[Segment] = []
        self._translations: dict[str, str] = {}
        self._loaded = False

    def get_segments(self) -> list[Segment]:
        """Return one ``Segment`` per ``page*.md`` file, naturally sorted."""
        self._ensure_loaded()
        return list(self._segments)

    def apply_translations(self, translated: list[TranslatedSegment]) -> None:
        """Store translations keyed by segment ID."""
        for ts in translated:
            self._translations[ts.id] = ts.translated

    def save(self, output_path: str) -> None:
        """Merge originals + translations into bilingual markdown."""
        self._ensure_loaded()
        merge = self._merge_fn
        if merge is None:
            from ai.bilingual_merger import BilingualMerger

            merge = BilingualMerger().merge

        originals: list[str] = []
        translations: list[str] = []
        for seg in self._segments:
            originals.append(seg.text)
            translations.append(self._translations.get(seg.id, ""))

        content = merge(originals, translations)
        Path(output_path).write_text(content, encoding="utf-8")

    # ── Internal ──────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        if not self._dir.is_dir():
            self._loaded = True
            return

        page_files = sorted(
            (f for f in self._dir.iterdir() if _PAGE_RE.match(f.name)),
            key=lambda f: f.name,
        )

        self._segments = [
            Segment(
                id=f.stem,
                text=f.read_text(encoding="utf-8"),
                metadata={"filename": f.name, "path": str(f)},
            )
            for f in page_files
        ]
        self._loaded = True
