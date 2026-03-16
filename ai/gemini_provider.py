from __future__ import annotations

import subprocess
from dataclasses import dataclass


VALID_MODELS: set[str] = {
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
}


@dataclass(slots=True)
class GeminiProvider:
    model: str

    def __post_init__(self) -> None:
        if self.model not in VALID_MODELS:
            raise ValueError(f"Unsupported Gemini model: {self.model}")

    def translate_chunk(
        self,
        text: str,
        chunk_size: int,
        system_prompt: str,
        timeout_seconds: int = 180,
    ) -> str:
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
            raise RuntimeError(f"Gemini CLI failed: {stderr}")

        return (result.stdout or "").strip()

