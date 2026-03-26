"""Gemini API provider using the google-genai SDK."""

from __future__ import annotations

import os
import re

try:
    from google import genai
    from google.genai import errors, types
except ImportError as exc:
    raise ImportError(
        "google-genai package required for GeminiAPIProvider. Install with: uv add google-genai"
    ) from exc


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
            resolved_model = "gemini-2.5-flash"
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
        self._client = genai.Client(api_key=self.api_key)

    def translate_chunk(
        self,
        *,
        text: str,
        chunk_size: int,
        system_prompt: str,
        timeout_seconds: int = 180,
    ) -> str:
        if chunk_size < 0:
            raise ValueError("chunk_size must be >= 0")
        if not text.strip():
            return ""

        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.3,
                    max_output_tokens=8192,
                    http_options=types.HttpOptions(timeout=timeout_seconds),
                ),
            )
            result_text = (response.text or "").strip()
            if not result_text:
                raise RuntimeError("Gemini API returned empty response")
            return result_text
        except errors.ClientError as exc:
            message = str(exc)
            code = getattr(exc, "code", None)
            if code == 429 or "RESOURCE_EXHAUSTED" in message:
                retry_after = _parse_retry_after(message)
                raise RateLimitError(f"Rate limit exceeded: {message}", retry_after) from exc
            if code == 408 or "timeout" in message.lower():
                raise RuntimeError(f"Gemini API request timeout after {timeout_seconds}s") from exc
            raise RuntimeError(f"Gemini API client error: {message}") from exc
        except errors.ServerError as exc:
            raise RuntimeError(f"Gemini API server error: {exc}") from exc
        except errors.APIError as exc:
            message = str(exc)
            if "timeout" in message.lower():
                raise RuntimeError(f"Gemini API request timeout after {timeout_seconds}s") from exc
            raise RuntimeError(f"Gemini API call failed: {message}") from exc
        except Exception as exc:
            raise RuntimeError(f"Gemini API call failed: {exc}") from exc
