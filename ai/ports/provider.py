"""Translation provider port — the contract backend adapters must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class TranslationError(Exception):
    """Raised when translation fails after adapter-level retries."""

    split_eligible = True


class RateLimitError(TranslationError):
    """Raised when the provider hits a rate limit."""

    split_eligible = False


class ProviderUnavailableError(TranslationError):
    """Infrastructure failure that must halt rather than split a content batch."""

    split_eligible = False


class ProviderAuthenticationError(ProviderUnavailableError):
    """The selected subscription runtime requires user authentication."""


class ProviderTimeoutError(ProviderUnavailableError):
    """The owned provider process exceeded its deadline."""


class ITranslationProvider(ABC):
    """Port for translation backends (Gemini CLI, Gemini API, etc.).

    Adapters handle transport-level details internally:
    - Prompt formatting and delimiter joining/splitting
    - Rate-limit back-off and transient-error retries
    - Response parsing and segment re-alignment

    The core engine never touches ``%%`` delimiters or raw API payloads.
    """

    @abstractmethod
    def translate_batch(
        self,
        segments: Sequence[str],
        *,
        system_prompt: str,
    ) -> list[str]:
        """Translate a batch of text segments.

        Args:
            segments: Ordered text segments to translate.
            system_prompt: System-level instructions for the model
                (language, glossary, style constraints, etc.).

        Returns:
            Translated segments in the **same order**.
            ``len(result) == len(segments)`` is a post-condition.

        Raises:
            TranslationError: If translation fails after adapter-level retries.
            RateLimitError: If the provider is rate-limited and back-off is
                exhausted.
        """
        ...
