from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Threshold:
    max_chars: int | None
    model: str


class ModelSelector:
    def __init__(self, config: dict[str, object]) -> None:
        thresholds = config.get("model_thresholds")
        if not isinstance(thresholds, dict):
            raise ValueError("config.model_thresholds must be a dictionary")

        self.small = self._parse_threshold(thresholds, "small")
        self.medium = self._parse_threshold(thresholds, "medium")
        self.large = self._parse_threshold(thresholds, "large")

    def _parse_threshold(self, thresholds: dict[str, object], key: str) -> Threshold:
        raw = thresholds.get(key)
        if not isinstance(raw, dict):
            raise ValueError(f"model_thresholds.{key} must be an object")

        max_chars_raw = raw.get("max_chars")
        if max_chars_raw is not None and not isinstance(max_chars_raw, int):
            raise ValueError(f"model_thresholds.{key}.max_chars must be int or null")
        model_raw = raw.get("model")
        if not isinstance(model_raw, str) or not model_raw:
            raise ValueError(f"model_thresholds.{key}.model must be non-empty string")

        return Threshold(max_chars=max_chars_raw, model=model_raw)

    def select(self, chunk_size: int) -> str:
        if chunk_size < 0:
            raise ValueError("chunk_size must be >= 0")

        if self.small.max_chars is not None and chunk_size < self.small.max_chars:
            return self.small.model
        if self.medium.max_chars is not None and chunk_size < self.medium.max_chars:
            return self.medium.model
        return self.large.model
