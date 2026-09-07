"""Fail-loud runtime configuration; examples and legacy paths are never defaults."""

from __future__ import annotations

import json
from pathlib import Path

from ai.core.config import ConfigRegistry


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Configuration must be an object")
    return dict(value)


def _validate(value: object, schema: dict[str, object], path: str) -> None:
    expected = schema.get("type")
    kinds = expected if isinstance(expected, list) else [expected]
    actual = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        dict: "object",
        type(None): "null",
    }.get(type(value))
    if actual not in kinds and not (actual == "integer" and "number" in kinds):
        raise ValueError(f"Invalid type at {path}")
    allowed = schema.get("enum")
    if isinstance(allowed, list) and value not in allowed:
        raise ValueError(f"Unsupported value at {path}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        for name in ("minimum", "maximum", "exclusiveMinimum"):
            limit = schema.get(name)
            if isinstance(limit, (int, float)):
                invalid = (
                    value < limit
                    if name == "minimum"
                    else value > limit
                    if name == "maximum"
                    else value <= limit
                )
                if invalid:
                    raise ValueError(f"Value out of range at {path}")
    if isinstance(value, dict):
        properties = _mapping(schema.get("properties", {}))
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("Configuration keys must be strings")
            child_schema = properties.get(key, schema.get("additionalProperties"))
            if not isinstance(child_schema, dict):
                raise ValueError(
                    f"Removed or unknown configuration key: {path}.{key}; migrate to the SPEC-021 configuration contract"
                )
            _validate(child, dict(child_schema), f"{path}.{key}")


def validate_config(config: dict[str, object]) -> dict[str, object]:
    schema_path = Path(__file__).resolve().parent.parent / "config/schemas/config_schema.json"
    schema = _mapping(json.loads(schema_path.read_text()))
    _validate(config, schema, "config")
    return config


def load_runtime_config() -> dict[str, object]:
    legacy = Path.home() / ".config/translatebook/config.json"
    if legacy.exists():
        raise ValueError(
            "Legacy ~/.config/translatebook/config.json exists; migrate it to ~/.config/bookweaver/config.json using SPEC-021"
        )
    root = Path(__file__).resolve().parent.parent
    paths = [root / "config/config.json", Path.home() / ".config/bookweaver/config.json"]
    for path in paths:
        if path.exists():
            try:
                validate_config(_mapping(json.loads(path.read_text())))
            except (OSError, ValueError) as exc:
                raise ValueError(
                    f"Invalid runtime configuration at {path}: {exc}; validate against config_schema.json"
                ) from exc
    return validate_config(ConfigRegistry.from_json_files(paths).to_dict())
