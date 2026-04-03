"""Gemini API adapter — wraps the legacy GeminiAPIProvider for the hexagonal port.

The API provider already has built-in retries, so this adapter is thinner
than the CLI variant.  It handles ``%%`` joining/splitting and maps
legacy errors to port error types.
"""

from __future__ import annotations

from collections.abc import Sequence

from ai.ports.provider import (
    ITranslationProvider,
    RateLimitError,
    TranslationError,
)

from ai.adapters.providers._delimiter import (
    augment_prompt_for_batch,
    join_segments,
    split_response,
)


class GeminiAPIAdapter(ITranslationProvider):
    """Adapter wrapping a raw Gemini API translator.

    Args:
        raw_provider: Any object with a ``translate_chunk(*, text,
            chunk_size, system_prompt, timeout_seconds)`` method
            (typically a legacy ``GeminiAPIProvider`` instance).
        timeout_seconds: Per-call API timeout.
    """

    def __init__(
        self,
        raw_provider: object,
        *,
        timeout_seconds: int = 600,
    ) -> None:
        self._raw = raw_provider
        self._timeout = timeout_seconds

    def translate_batch(
        self,
        segments: Sequence[str],
        *,
        system_prompt: str,
    ) -> list[str]:
        seg_list = list(segments)
        if not seg_list:
            return []

        joined = join_segments(seg_list)
        prompt = augment_prompt_for_batch(system_prompt, len(seg_list))

        try:
            raw_result: str = self._raw.translate_chunk(  # type: ignore[union-attr]
                text=joined,
                chunk_size=len(joined),
                system_prompt=prompt,
                timeout_seconds=self._timeout,
            )
        except Exception as exc:
            if self._is_rate_limit(exc):
                raise RateLimitError(str(exc)) from exc
            raise TranslationError(str(exc)) from exc

        return split_response(raw_result, len(seg_list))

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        return type(exc).__name__ == "RateLimitError"
