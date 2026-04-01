"""Configuration registry with layered JSON loading and typed lookup."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import TypeVar

_T = TypeVar("_T")
_MISSING = object()


class ConfigRegistry:
    """Holds merged runtime configuration and exposes typed dotted-key getters."""

    _TRUE_VALUES = {"1", "true", "yes", "on"}
    _FALSE_VALUES = {"0", "false", "no", "off"}

    def __init__(self, data: dict[str, object] | None = None) -> None:
        self._data: dict[str, object] = deepcopy(data or {})

    @classmethod
    def from_json_files(cls, paths: list[Path]) -> "ConfigRegistry":
        """Load and deep-merge JSON config files in order.

        Later files override earlier files.
        Missing paths are ignored.
        """
        merged: dict[str, object] = {}
        for path in paths:
            if not path.exists():
                continue
            loaded = _load_json_object(path)
            merged = _deep_merge(merged, loaded)
        return cls(merged)

    def to_dict(self) -> dict[str, object]:
        """Return a defensive deep copy of the merged configuration."""
        return deepcopy(self._data)

    def get(self, dotted_key: str, default: _T | None = None) -> object | _T | None:
        value = _dotted_lookup(self._data, dotted_key)
        if value is _MISSING:
            return default
        return value

    def get_str(self, dotted_key: str, default: str | None = None) -> str | None:
        value = self.get(dotted_key)
        if value is None:
            return default
        if isinstance(value, str):
            return value
        return str(value)

    def get_bool(self, dotted_key: str, default: bool | None = None) -> bool | None:
        value = self.get(dotted_key)
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            bool_value = _parse_bool_string(
                normalized,
                true_values=self._TRUE_VALUES,
                false_values=self._FALSE_VALUES,
            )
            if bool_value is not None:
                return bool_value
        return default

    def get_int(self, dotted_key: str, default: int | None = None) -> int | None:
        value = self.get(dotted_key)
        return _coerce_int(value, default=default)


def _load_json_object(path: Path) -> dict[str, object]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        msg = f"Config at {path} must be a JSON object"
        raise ValueError(msg)
    return data


def _deep_merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = deepcopy(base)
    for key, value in override.items():
        current = result.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            result[key] = _deep_merge(current, value)
        else:
            result[key] = deepcopy(value)
    return result


def _dotted_lookup(data: dict[str, object], dotted_key: str) -> object:
    if not dotted_key:
        return _MISSING
    current: object = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _parse_bool_string(
    value: str,
    *,
    true_values: set[str],
    false_values: set[str],
) -> bool | None:
    if value in true_values:
        return True
    if value in false_values:
        return False
    return None


def _coerce_int(value: object, *, default: int | None) -> int | None:
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            return default
    return default
