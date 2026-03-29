"""Translation engine — the core orchestrator.

Coordinates the pipeline: extract segments → batch → translate → apply → save.
Depends only on ports (``ITranslationProvider``, ``IBookSource``) and the
``TextBatcher``.  Knows nothing about EPUB structure, ``%%`` delimiters,
or specific API transports.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ai.core.batcher import TextBatcher
from ai.ports.provider import ITranslationProvider, TranslationError
from ai.ports.source import IBookSource, TranslatedSegment


@dataclass(frozen=True)
class EngineConfig:
    """Immutable configuration for the translation engine.

    Attributes:
        system_prompt: Pre-built system prompt (language, glossary,
            style constraints, etc.).  The engine passes this verbatim
            to the provider; prompt *assembly* is the caller's job.
        max_batch_chars: Maximum total characters per batch.
        separator_overhead: Per-separator char count the adapter will
            insert between segments (e.g. ``len("\\n\\n%%\\n\\n") == 6``).
        max_split_depth: Maximum binary-split recursion depth when a
            batch translation fails persistently.
    """

    system_prompt: str
    max_batch_chars: int = 60_000
    separator_overhead: int = 6
    max_split_depth: int = 10


@dataclass
class TranslationResult:
    """Summary returned after a translation run."""

    total_segments: int
    total_batches: int
    translated_segments: int


class TranslationEngine:
    """Orchestrates: extract → batch → translate → apply → save.

    Resilience strategy: if the provider raises :class:`TranslationError`
    on a multi-segment batch, the engine splits the batch in half and
    retries each half independently.  This continues up to
    ``config.max_split_depth`` levels.  Single-segment failures propagate
    immediately.
    """

    def __init__(
        self,
        provider: ITranslationProvider,
        config: EngineConfig,
    ) -> None:
        self._provider = provider
        self._config = config
        self._batcher = TextBatcher(
            max_batch_chars=config.max_batch_chars,
            separator_overhead=config.separator_overhead,
        )

    def translate(
        self,
        source: IBookSource,
        output_path: str,
        *,
        on_batch_translated: Callable[[int, int], None] | None = None,
    ) -> TranslationResult:
        """Run the full translation pipeline.

        Args:
            source: Book source adapter to read segments from and write
                translations back to.
            output_path: Destination file path for the translated document.
            on_batch_translated: Optional callback ``(batch_index, total_batches)``
                invoked after each batch is translated.

        Returns:
            Summary of the translation run.

        Raises:
            TranslationError: If a segment fails after all split-retry
                attempts are exhausted.
        """
        segments = source.get_segments()
        if not segments:
            source.save(output_path)
            return TranslationResult(
                total_segments=0, total_batches=0, translated_segments=0
            )

        texts = [s.text for s in segments]
        batches = self._batcher.plan_batches(texts)

        all_translated: list[str] = []
        for i, batch in enumerate(batches):
            translated = self._translate_with_resilience(batch)
            all_translated.extend(translated)
            if on_batch_translated is not None:
                on_batch_translated(i, len(batches))

        translated_segments = [
            TranslatedSegment(id=seg.id, original=seg.text, translated=text)
            for seg, text in zip(segments, all_translated, strict=True)
        ]

        source.apply_translations(translated_segments)
        source.save(output_path)

        return TranslationResult(
            total_segments=len(segments),
            total_batches=len(batches),
            translated_segments=len(all_translated),
        )

    # ── Resilience ────────────────────────────────────────────

    def _translate_with_resilience(
        self,
        segments: list[str],
        *,
        _depth: int = 0,
    ) -> list[str]:
        """Translate *segments* with binary-split resilience.

        On :class:`TranslationError`, splits the batch in half and
        retries each half.  Recursion stops at ``max_split_depth``
        or when only one segment remains.
        """
        try:
            return self._provider.translate_batch(
                segments, system_prompt=self._config.system_prompt
            )
        except TranslationError:
            can_split = len(segments) > 1 and _depth < self._config.max_split_depth
            if not can_split:
                raise

            mid = len(segments) // 2
            left = self._translate_with_resilience(
                segments[:mid], _depth=_depth + 1
            )
            right = self._translate_with_resilience(
                segments[mid:], _depth=_depth + 1
            )
            return left + right
