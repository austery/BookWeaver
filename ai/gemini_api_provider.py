"""Gemini API provider using google-generativeai SDK.

Alternative to GeminiProvider (CLI-based). Uses direct API calls for better
error handling, retry control, and stability.

Note: Using google-generativeai SDK (deprecated). Will migrate to google-genai
SDK when stable and well-documented. Current SDK is stable enough for our use case.
"""

from __future__ import annotations

import os
import re
import warnings

try:
    import google.generativeai as genai
    from google.api_core.exceptions import (
        DeadlineExceeded,
        InternalServerError,
        ResourceExhausted,
        ServiceUnavailable,
    )

    # Suppress deprecation warning from google.generativeai
    warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")
except ImportError as exc:
    raise ImportError(
        "google-generativeai package required for GeminiAPIProvider. "
        "Install with: uv add google-generativeai"
    ) from exc


class RateLimitError(RuntimeError):
    """Raised when Gemini API returns 429 / RESOURCE_EXHAUSTED."""

    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def _parse_retry_after(error_message: str) -> int | None:
    """Extract retry delay seconds from error message.

    Tries to parse patterns like:
    - "Retry in 30 seconds"
    - "retry after 45s"
    - "retryDelay: 60s"
    """
    # Pattern 1: "retry in N seconds" or "retry after N seconds"
    match = re.search(r"retry (?:in|after) (\d+)\s*(?:second|s)", error_message, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # Pattern 2: "retryDelay: Ns" or "retryDelay: N"
    match = re.search(r"retryDelay[\"']?\s*[:=]\s*[\"']?(\d+)", error_message, re.IGNORECASE)
    if match:
        return int(match.group(1))

    return None


class GeminiAPIProvider:
    """Gemini API provider using google-generativeai SDK."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash",
    ) -> None:
        """Initialize Gemini API provider.

        Args:
            api_key: Google AI API key. If None, reads from GEMINI_API_KEY env var.
            model: Model name (default: gemini-2.5-flash)

        Raises:
            ValueError: If API key is empty or not provided
        """
        resolved_api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not resolved_api_key:
            raise ValueError(
                "API key is required. Provide via api_key parameter or GEMINI_API_KEY env var."
            )

        self.api_key = resolved_api_key
        self.model = model

        # Configure genai SDK
        genai.configure(api_key=self.api_key)

    def translate_chunk(
        self,
        *,
        text: str,
        chunk_size: int,
        system_prompt: str,
        timeout_seconds: int = 180,
    ) -> str:
        """Translate a text chunk using Gemini API.

        Args:
            text: Source text to translate
            chunk_size: Size of chunk (for logging only)
            system_prompt: System prompt with translation instructions
            timeout_seconds: Request timeout in seconds (default: 180)

        Returns:
            Translated text

        Raises:
            RateLimitError: On 429 rate limit / quota exhausted
            RuntimeError: On other API errors, empty response, or timeout
        """
        try:
            # Create model with system instruction
            model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=system_prompt,
            )

            # Generate content with timeout
            # Note: google-generativeai SDK doesn't directly support timeout parameter
            # We rely on SDK's default timeout or handle DeadlineExceeded exception
            response = model.generate_content(
                text,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=8192,
                ),
                request_options={"timeout": timeout_seconds},
            )

            result_text = response.text or ""

            if not result_text:
                raise RuntimeError("Gemini API returned empty response")

            return result_text

        except ResourceExhausted as exc:
            # 429 rate limit or quota exceeded
            error_msg = str(exc)
            retry_after = _parse_retry_after(error_msg)
            raise RateLimitError(f"Rate limit exceeded: {error_msg}", retry_after) from exc

        except DeadlineExceeded as exc:
            raise RuntimeError(f"Gemini API request timeout after {timeout_seconds}s") from exc

        except (InternalServerError, ServiceUnavailable) as exc:
            # 5xx server errors
            raise RuntimeError(f"Gemini API server error: {exc}") from exc

        except Exception as exc:
            # Catch-all for other errors
            raise RuntimeError(f"Gemini API call failed: {exc}") from exc
