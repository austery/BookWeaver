from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


class RateLimitError(RuntimeError):
    """Raised when Gemini CLI returns 429 / RESOURCE_EXHAUSTED."""

    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def _parse_retry_after(stderr: str) -> int | None:
    """Extract retry delay seconds from Gemini CLI stderr.

    Tries JSON format first (``"retryDelay": "30s"``), then natural-language
    format (``"retry after 30 seconds"``). Returns ``None`` if neither is found.
    """
    m = re.search(r'"retryDelay":\s*"(\d+)s"', stderr)
    if m:
        return int(m.group(1))
    m = re.search(r"retry after (\d+)", stderr, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


@dataclass(slots=True)
class GeminiProvider:
    model: str

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("Gemini model must be a non-empty string")

    def translate_chunk(
        self,
        text: str,
        chunk_size: int,
        system_prompt: str,
        timeout_seconds: int = 180,
    ) -> str:
        # chunk_size is reserved for future rate-limiting; it is not used
        # functionally in the current implementation.
        if chunk_size < 0:
            raise ValueError("chunk_size must be >= 0")
        if not text.strip():
            return ""

        prompt = f"{system_prompt}\n\n{text}"
        result = subprocess.run(
            ["gemini", "--model", self.model],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            if "429" in stderr or "RESOURCE_EXHAUSTED" in stderr:
                wait = _parse_retry_after(stderr)
                raise RateLimitError(f"Gemini rate limited: {stderr}", retry_after_seconds=wait)
            raise RuntimeError(f"Gemini CLI failed: {stderr}")

        return (result.stdout or "").strip()
