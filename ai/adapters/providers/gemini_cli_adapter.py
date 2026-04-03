"""Gemini CLI adapter — wraps the legacy GeminiProvider for the hexagonal port.

Handles protocol-aware batch framing/parsing and transport-level retries
(rate-limit, transient errors) internally. The core engine sees only the
clean ``ITranslationProvider.translate_batch`` interface.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from ai.ports.provider import (
    ITranslationProvider,
    RateLimitError,
    TranslationError,
)

from ai.adapters.providers._delimiter import (
    PROTOCOL_DELIMITER,
    PROTOCOL_SEGMENT_TAGS,
    augment_prompt_for_batch,
    join_segments,
    split_response,
)


class GeminiCLIAdapter(ITranslationProvider):
    """Adapter wrapping a raw Gemini CLI translator.

    Args:
        raw_provider: Any object with a ``translate_chunk(text, chunk_size,
            system_prompt, timeout_seconds)`` method (typically a legacy
            ``GeminiProvider`` instance).
        timeout_seconds: Per-call subprocess timeout.
        rate_limit_backoff: Backoff delays (seconds) for rate-limit retries.
        transient_backoff: Backoff delays (seconds) for transient-error retries.
        sleep_fn: Injectable sleep function (for testing).
    """

    def __init__(
        self,
        raw_provider: object,
        *,
        timeout_seconds: int = 600,
        rate_limit_backoff: tuple[int, ...] = (60, 120),
        transient_backoff: tuple[int, ...] = (45,),
        use_segment_tags: bool = False,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._raw = raw_provider
        self._timeout = timeout_seconds
        self._use_segment_tags = use_segment_tags
        self._rate_limit_backoff = self._validate_backoff(
            rate_limit_backoff,
            label="rate_limit_backoff",
        )
        self._transient_backoff = self._validate_backoff(
            transient_backoff,
            label="transient_backoff",
        )
        self._sleep = sleep_fn

    def translate_batch(
        self,
        segments: Sequence[str],
        *,
        system_prompt: str,
    ) -> list[str]:
        seg_list = list(segments)
        if not seg_list:
            return []

        protocol = self._get_protocol()
        joined = join_segments(seg_list, protocol=protocol)
        prompt = augment_prompt_for_batch(system_prompt, len(seg_list), protocol=protocol)

        raw_result = self._call_with_retry(joined, prompt)

        return split_response(raw_result, len(seg_list), protocol=protocol)

    def _get_protocol(self) -> str:
        if self._use_segment_tags:
            return PROTOCOL_SEGMENT_TAGS
        return PROTOCOL_DELIMITER

    # ── Internal retry logic ──────────────────────────────────

    def _call_with_retry(self, text: str, prompt: str) -> str:
        """Call the raw translator with rate-limit and transient retries."""
        rate_budget = list(self._rate_limit_backoff)
        transient_budget = list(self._transient_backoff)
        transient_attempts = 0

        while True:
            try:
                return self._raw.translate_chunk(  # type: ignore[union-attr]
                    text=text,
                    chunk_size=len(text),
                    system_prompt=prompt,
                    timeout_seconds=self._timeout,
                )
            except Exception as exc:
                if self._is_rate_limit(exc):
                    if not rate_budget:
                        raise RateLimitError(str(exc)) from exc
                    self._sleep(rate_budget.pop(0))
                elif self._is_transient(exc):
                    transient_attempts += 1
                    if not transient_budget:
                        configured_retries = len(self._transient_backoff)
                        raise TranslationError(
                            "Transient CLI retries exhausted after "
                            f"{transient_attempts} attempts (configured retries: "
                            f"{configured_retries}): {exc}"
                        ) from exc
                    self._sleep(transient_budget.pop(0))
                else:
                    raise TranslationError(str(exc)) from exc

    @staticmethod
    def _validate_backoff(
        values: tuple[int, ...],
        *,
        label: str,
    ) -> tuple[int, ...]:
        if any(
            isinstance(value, bool) or (not isinstance(value, int)) or value <= 0
            for value in values
        ):
            raise ValueError(f"{label} values must be positive integers")
        return values

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        return type(exc).__name__ == "RateLimitError"

    @staticmethod
    def _is_transient(exc: Exception) -> bool:
        return type(exc).__name__ == "TransientCLIError"
