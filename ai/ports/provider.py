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


class ProviderQuotaError(ProviderUnavailableError):
    """The subscription runtime refused the request because its quota is used up."""


class ProviderTimeoutError(ProviderUnavailableError):
    """The owned provider process exceeded its deadline."""


class OutputTruncatedError(ProviderUnavailableError):
    """The model stopped at its output-token cap; the batch translation is incomplete."""


class ITranslationProvider(ABC):
    """Port for translation backends (Gemini CLI, Gemini API, etc.).

    Adapters handle transport-level details internally:
    - Prompt formatting and delimiter joining/splitting
    - Rate-limit back-off and transient-error retries
    - Response parsing and segment re-alignment

    The core engine never touches ``%%`` delimiters or raw API payloads.
    """

    # Unavailable until discovery, or for transports without a runtime version.
    runtime_version: str | None = None
    # Concrete execution backend recorded as segment provenance (e.g. "antigravity").
    backend: str | None = None

    def check_ready(self) -> None:
        """Confirm the runtime is reachable, and signed in where it can tell, without a model call.

        Raises a ``ProviderUnavailableError`` subtype when it is not. Transports with nothing to
        check do nothing. A Term Panel calls this for every member before its first model call.
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
