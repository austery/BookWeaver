"""Book source port — the contract format adapters must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Segment:
    """A translatable unit extracted from a book.

    Attributes:
        id: Stable identifier (e.g. ``chapter-3/p-17``).
        text: Source-language text content.
        metadata: Format-specific hints the adapter may attach
            (chapter title, element tag, …).  The core engine
            treats this as opaque pass-through data.
    """

    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TranslatedSegment:
    """A segment paired with its translation."""

    id: str
    original: str
    translated: str


class IBookSource(ABC):
    """Port for book format adapters (EPUB, Markdown, DOCX, etc.).

    Adapters handle format-specific structure internally:
    - EPUB: chapters, TOC, manifest, spine ordering, package lifecycle
    - Markdown: file splitting, heading detection
    - DOCX: paragraph/table extraction

    The engine sees only a flat list of :class:`Segment` objects.
    """

    @abstractmethod
    def get_segments(self) -> list[Segment]:
        """Extract translatable segments from the source.

        Returns:
            Ordered list of segments.  Order is preserved through
            the translate → apply round-trip.
        """
        ...

    @abstractmethod
    def apply_translations(self, translated: list[TranslatedSegment]) -> None:
        """Apply translations back to the source structure.

        The adapter maps each :class:`TranslatedSegment` back to its
        format-specific location using the segment ``id``.

        Args:
            translated: Segments with their translations, in any order
                (matched by ``id``).
        """
        ...

    @abstractmethod
    def save(self, output_path: str) -> None:
        """Write the translated document to *output_path*.

        The format is determined by the adapter (e.g. ``.epub``,
        ``.md``, ``.docx``).
        """
        ...
