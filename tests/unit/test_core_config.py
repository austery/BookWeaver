from __future__ import annotations

import json
from pathlib import Path

from ai.core.config import ConfigRegistry


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_from_json_files_deep_merge_later_files_override(tmp_path: Path) -> None:
    base = tmp_path / "config.base.json"
    override = tmp_path / "config.override.json"

    _write_json(
        base,
        {
            "default_model": "gemini-2.5-flash",
            "gemini_api": {"enabled": True, "api_key": None},
            "model_probe": {"enabled": True, "cache_ttl_seconds": 3600},
        },
    )
    _write_json(
        override,
        {
            "default_model": "gemini-2.5-pro",
            "gemini_api": {"api_key": "abc"},
            "model_probe": {"cache_ttl_seconds": 600},
        },
    )

    cfg = ConfigRegistry.from_json_files([base, override])

    assert cfg.get_str("default_model") == "gemini-2.5-pro"
    assert cfg.get_bool("gemini_api.enabled") is True
    assert cfg.get_str("gemini_api.api_key") == "abc"
    assert cfg.get_int("model_probe.cache_ttl_seconds") == 600


def test_from_json_files_skips_missing_paths(tmp_path: Path) -> None:
    existing = tmp_path / "config.json"
    _write_json(existing, {"default_model": "gemini-2.5-flash"})

    cfg = ConfigRegistry.from_json_files([tmp_path / "missing.json", existing])

    assert cfg.get_str("default_model") == "gemini-2.5-flash"


def test_dotted_get_returns_default_for_missing_key() -> None:
    cfg = ConfigRegistry({"gemini_api": {"enabled": True}})

    assert cfg.get("gemini_api.timeout", 180) == 180
    assert cfg.get_str("gemini_api.api_key", "fallback") == "fallback"


def test_typed_getters_convert_common_primitives() -> None:
    cfg = ConfigRegistry(
        {
            "flags": {
                "from_bool": True,
                "from_yes": "yes",
                "from_zero": "0",
                "bad_bool": "unknown",
            },
            "limits": {"from_int": 300, "from_str": "120", "bad_int": "abc"},
        }
    )

    assert cfg.get_bool("flags.from_bool") is True
    assert cfg.get_bool("flags.from_yes") is True
    assert cfg.get_bool("flags.from_zero") is False
    assert cfg.get_bool("flags.bad_bool", default=False) is False

    assert cfg.get_int("limits.from_int") == 300
    assert cfg.get_int("limits.from_str") == 120
    assert cfg.get_int("limits.bad_int", default=42) == 42

