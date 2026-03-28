"""Gemini API provider using the google-genai SDK."""

from __future__ import annotations

import logging
import os
import re
import time

try:
    from google import genai
    from google.genai import errors, types
except ImportError as exc:
    raise ImportError(
        "google-genai package required for GeminiAPIProvider. Install with: uv add google-genai"
    ) from exc

logger = logging.getLogger(__name__)


class RateLimitError(RuntimeError):
    """Raised when Gemini API returns 429 / RESOURCE_EXHAUSTED."""

    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def _parse_retry_after(error_message: str) -> int | None:
    """Extract retry delay seconds from error message."""
    match = re.search(r"retry (?:in|after) (\d+)\s*(?:second|s)", error_message, re.IGNORECASE)
    if match:
        return int(match.group(1))

    match = re.search(r"retryDelay[\"']?\s*[:=]\s*[\"']?(\d+)", error_message, re.IGNORECASE)
    if match:
        return int(match.group(1))

    return None


class GeminiAPIProvider:
    """Gemini API provider using google-genai SDK."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        config: dict[str, object] | None = None,
    ) -> None:
        resolved_api_key = api_key or os.getenv("GEMINI_API_KEY", "")

        if not resolved_api_key and config:
            gemini_api_config = config.get("gemini_api")
            if isinstance(gemini_api_config, dict):
                from_config = gemini_api_config.get("api_key")
                if isinstance(from_config, str):
                    resolved_api_key = from_config

        if not resolved_api_key:
            raise ValueError(
                "API key is required. Provide via:\n"
                "  1. api_key parameter\n"
                "  2. GEMINI_API_KEY environment variable\n"
                "  3. config['gemini_api']['api_key'] in config.json"
            )

        if model is None:
            resolved_model = "gemini-1.5-flash"
            if config:
                gemini_api_config = config.get("gemini_api")
                if isinstance(gemini_api_config, dict):
                    config_model = gemini_api_config.get("model")
                    if isinstance(config_model, str) and config_model:
                        resolved_model = config_model
        else:
            resolved_model = model

        self.api_key = resolved_api_key
        self.model = resolved_model
        self._client = genai.GenerativeModel(
            self.model,
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
        )

    def translate_chunk(
        self,
        *,
        text: str,
        chunk_size: int,
        system_prompt: str,
        timeout_seconds: int = 180,
        max_retries: int = 3,
        retry_delay_seconds: int = 1,
    ) -> str:
        if chunk_size < 0:
            raise ValueError("chunk_size must be >= 0")
        if not text.strip():
            return ""

        last_exception: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = self._client.generate_content(
                    contents=text,
                    generation_config=types.GenerationConfig(
                        temperature=0.3,
                        max_output_tokens=8192,
                    ),
                    request_options={"timeout": timeout_seconds},
                )
                result_text = (response.text or "").strip()
                if not result_text:
                    raise RuntimeError("Gemini API returned empty response")
                return result_text
            except RateLimitError as exc:
                last_exception = exc
                wait_time = exc.retry_after_seconds or retry_delay_seconds
                logger.warning(
                    f"Rate limit exceeded. Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)
            except (errors.ServerError, errors.InternalServerError) as exc:
                last_exception = exc
                logger.warning(
                    f"Gemini API server error: {exc}. Retrying in {retry_delay_seconds}s... (Attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(retry_delay_seconds)
            except errors.ClientError as exc:
                message = str(exc)
                code = getattr(exc, "code", None)
                if code == 429 or "RESOURCE_EXHAUSTED" in message:
                    retry_after = _parse_retry_after(message)
                    last_exception = RateLimitError(f"Rate limit exceeded: {message}", retry_after)
                    wait_time = retry_after or retry_delay_seconds
                    logger.warning(
                        f"Rate limit detected. Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                elif code == 408 or "timeout" in message.lower():
                    last_exception = RuntimeError(
                        f"Gemini API request timeout after {timeout_seconds}s"
                    )
                    logger.warning(
                        f"Gemini API timeout. Retrying in {retry_delay_seconds}s... (Attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(retry_delay_seconds)
                else:
                    raise RuntimeError(f"Gemini API client error: {message}") from exc
            except errors.APIError as exc:
                message = str(exc)
                if "timeout" in message.lower():
                    last_exception = RuntimeError(
                        f"Gemini API request timeout after {timeout_seconds}s"
                    )
                    logger.warning(
                        f"Gemini API timeout. Retrying in {retry_delay_seconds}s... (Attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(retry_delay_seconds)
                else:
                    raise RuntimeError(f"Gemini API call failed: {message}") from exc
            except Exception as exc:
                last_exception = exc
                logger.warning(
                    f"An unexpected error occurred: {exc}. Retrying in {retry_delay_seconds}s... (Attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(retry_delay_seconds)

        if last_exception:
            raise last_exception
        raise RuntimeError("Gemini API call failed after multiple retries")
