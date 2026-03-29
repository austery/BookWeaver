"""Markdown source adapter — reads split ``page*.md`` directories.

Handles the split-Markdown format produced by ``02_split_to_md.py``.
Each page file is split into **block-level** segments (paragraphs,
headings, code blocks, lists) so the bilingual output alternates
paragraph-by-paragraph instead of one giant English/Chinese block.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from ai.ports.source import IBookSource, Segment, TranslatedSegment

_PAGE_RE = re.compile(r"^page[_\-]?\d+\.md$")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")


def _split_blocks(text: str) -> list[str]:
    """Split markdown into block-level elements.

    Blank-line separated, but fenced code blocks are kept atomic.
    Empty blocks are discarded.
    """
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    fence_marker = ""

    for line in text.splitlines():
        fence_match = _FENCE_RE.match(line.strip())
        if fence_match and not in_fence:
            # Start of fenced code block — flush any pending block first
            if current:
                blocks.append("\n".join(current))
                current = []
            in_fence = True
            fence_marker = fence_match.group(1)[0]
            current.append(line)
        elif (
            in_fence
            and line.strip().startswith(fence_marker)
            and len(line.strip().rstrip(fence_marker[0])) == 0
        ):
            # End of fenced code block
            current.append(line)
            blocks.append("\n".join(current))
            current = []
            in_fence = False
            fence_marker = ""
        elif in_fence:
            current.append(line)
        elif line.strip() == "":
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(line)

    if current:
        blocks.append("\n".join(current))

    return [b for b in blocks if b.strip()]


def _is_fenced_code_block(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False

    lines = stripped.splitlines()
    if len(lines) < 2:
        return False

    start = lines[0].strip()
    end = lines[-1].strip()
    start_match = _FENCE_RE.match(start)
    if start_match is None:
        return False

    marker = start_match.group(1)
    return end.startswith(marker[0] * 3)


def _render_clean_bilingual(
    segments: list[Segment],
    translations: dict[str, str],
) -> str:
    """Render markdown in clean alternating bilingual layout.

    For each segment: original block, one blank line, translated block.
    For fenced code blocks, avoid duplication when translation is unchanged.
    """
    blocks: list[str] = []

    for seg in segments:
        original = seg.text.strip()
        translated = translations.get(seg.id, "").strip()
        if not original and not translated:
            continue

        if _is_fenced_code_block(original):
            # Code block rule: output only once. Prefer translated variant
            # when available (e.g., translated comments inside code).
            blocks.append(translated or original)
            continue

        if translated and translated == original:
            # Identical text rule: output only once.
            blocks.append(original)
            continue

        blocks.append(original)
        if translated:
            blocks.append(translated)

    if not blocks:
        return ""
    return "\n\n".join(blocks).strip() + "\n"


class MarkdownSourceAdapter(IBookSource):
    """Adapter for split-Markdown directories (``page*.md`` files).

    Each page file is parsed into block-level segments so translations
    alternate paragraph-by-paragraph in the output.

    Args:
        markdown_dir: Directory containing ``page*.md`` files.
        _merge_fn: Optional injectable merge callable for tests.
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
        """Return block-level ``Segment`` objects, naturally sorted by page."""
        self._ensure_loaded()
        return list(self._segments)

    def apply_translations(self, translated: list[TranslatedSegment]) -> None:
        """Store translations keyed by segment ID."""
        for ts in translated:
            self._translations[ts.id] = ts.translated

    def save(self, output_path: str) -> None:
        """Render clean alternating bilingual markdown."""
        self._ensure_loaded()
        merge = self._merge_fn
        if merge is None:
            content = _render_clean_bilingual(self._segments, self._translations)
        else:
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

        for f in page_files:
            text = f.read_text(encoding="utf-8")
            blocks = _split_blocks(text)
            for idx, block in enumerate(blocks):
                self._segments.append(
                    Segment(
                        id=f"{f.stem}::{idx}",
                        text=block,
                        metadata={"filename": f.name, "path": str(f), "block_index": idx},
                    )
                )

        self._loaded = True
