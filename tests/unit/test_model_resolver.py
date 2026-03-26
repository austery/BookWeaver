from __future__ import annotations

import pytest

from ai.model_resolver import ModelResolver, ModelRole, ResolvedModel


# ─── Basic alias resolution ────────────────────────────────────────────────


def test_resolves_alias_from_config() -> None:
    config = {"model_aliases": {"pro": "gemini-2.5-pro"}}
    result = ModelResolver(config).resolve("pro")
    assert result.name == "gemini-2.5-pro"
    assert result.role == ModelRole.PRO


def test_builtin_fallback_when_config_has_no_aliases() -> None:
    result = ModelResolver({}).resolve("pro")
    assert result.name == "gemini-2.5-pro"
    assert result.role == ModelRole.PRO


def test_config_alias_overrides_builtin() -> None:
    config = {"model_aliases": {"pro": "gemini-2.5-pro-exp"}}
    result = ModelResolver(config).resolve("pro")
    assert result.name == "gemini-2.5-pro-exp"
    assert result.role == ModelRole.PRO


def test_resolves_flash_alias() -> None:
    result = ModelResolver({}).resolve("flash")
    assert result.name == "gemini-2.5-flash"
    assert result.role == ModelRole.FLASH


def test_resolves_lite_alias() -> None:
    result = ModelResolver({}).resolve("lite")
    assert result.name == "gemini-2.5-flash-lite"
    assert result.role == ModelRole.LITE


def test_passthrough_for_unknown_full_name() -> None:
    result = ModelResolver({}).resolve("gemini-99-ultra")
    assert result.name == "gemini-99-ultra"
    assert result.role == ModelRole.UNKNOWN


def test_direct_pro_full_name_gets_pro_role() -> None:
    """Passing full model name directly must resolve to correct role via inverted map."""
    result = ModelResolver({}).resolve("gemini-2.5-pro")
    assert result.name == "gemini-2.5-pro"
    assert result.role == ModelRole.PRO


def test_direct_flash_full_name_gets_flash_role() -> None:
    result = ModelResolver({}).resolve("gemini-2.5-flash")
    assert result.name == "gemini-2.5-flash"
    assert result.role == ModelRole.FLASH


# ─── resolve_alias: alias-only (no probe/fallback) ────────────────────────


def test_resolve_alias_only_returns_alias_step() -> None:
    """resolve_alias() does pure alias chain — no probe, no fallback."""
    config = {
        "model_aliases": {"pro": "gemini-2.5-pro"},
        "model_probe": {"enabled": False},
    }
    result = ModelResolver(config).resolve_alias("pro")
    assert result.name == "gemini-2.5-pro"
    assert result.role == ModelRole.PRO


def test_resolve_alias_direct_full_name() -> None:
    result = ModelResolver({}).resolve_alias("gemini-2.5-pro")
    assert result.name == "gemini-2.5-pro"
    assert result.role == ModelRole.PRO


# ─── Alias cycles ─────────────────────────────────────────────────────────


def test_alias_cycle_raises_value_error() -> None:
    config = {"model_aliases": {"pro": "flash", "flash": "pro"}}
    with pytest.raises(ValueError, match="cycle detected"):
        ModelResolver(config).resolve("pro")


def test_alias_cycle_in_resolve_alias_raises() -> None:
    config = {"model_aliases": {"pro": "flash", "flash": "pro"}}
    with pytest.raises(ValueError, match="cycle detected"):
        ModelResolver(config).resolve_alias("pro")


def test_empty_requested_raises_value_error() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        ModelResolver({}).resolve("  ")


# ─── Probe disabled ───────────────────────────────────────────────────────


def test_no_probe_returns_primary_directly() -> None:
    config = {"model_probe": {"enabled": False}, "model_aliases": {"pro": "gemini-2.5-pro"}}
    result = ModelResolver(config).resolve("pro")
    assert result.name == "gemini-2.5-pro"
    assert result.role == ModelRole.PRO


# ─── Probe enabled (injected for unit testing) ────────────────────────────


class _FakeProbe:
    def __init__(self, available: set[str]) -> None:
        self.available = available
        self.last_probe_errors: dict[str, str] = {}

    def probe(self, candidates: list[str]) -> dict[str, bool]:
        return {c: c in self.available for c in candidates}


def test_probe_returns_first_available_fallback() -> None:
    config = {
        "model_aliases": {"pro": "gemini-2.5-pro", "flash": "gemini-2.5-flash"},
        "fallback_chain": ["flash"],
        "enable_fallback": True,
        "model_probe": {"enabled": True},
    }
    probe = _FakeProbe(available={"gemini-2.5-flash"})
    result = ModelResolver(config, probe=probe).resolve("pro")
    assert result.name == "gemini-2.5-flash"
    assert result.role == ModelRole.FLASH


def test_probe_primary_available_returns_primary() -> None:
    config = {
        "model_aliases": {"pro": "gemini-2.5-pro", "flash": "gemini-2.5-flash"},
        "fallback_chain": ["flash"],
        "enable_fallback": True,
        "model_probe": {"enabled": True},
    }
    probe = _FakeProbe(available={"gemini-2.5-pro", "gemini-2.5-flash"})
    result = ModelResolver(config, probe=probe).resolve("pro")
    assert result.name == "gemini-2.5-pro"
    assert result.role == ModelRole.PRO


def test_probe_all_fail_warns_and_returns_primary() -> None:
    config = {
        "model_aliases": {"pro": "gemini-2.5-pro", "flash": "gemini-2.5-flash"},
        "fallback_chain": ["flash"],
        "enable_fallback": True,
        "model_probe": {"enabled": True},
    }
    probe = _FakeProbe(available=set())
    with pytest.warns(RuntimeWarning, match="All model candidates unavailable"):
        result = ModelResolver(config, probe=probe).resolve("pro")
    assert result.name == "gemini-2.5-pro"
    assert result.role == ModelRole.PRO


def test_probe_without_enable_fallback_only_probes_primary() -> None:
    """enable_fallback=False: candidates list contains only primary, not fallback_chain entries."""
    config = {
        "model_aliases": {"pro": "gemini-2.5-pro", "flash": "gemini-2.5-flash"},
        "fallback_chain": ["flash"],
        "enable_fallback": False,
        "model_probe": {"enabled": True},
    }
    probed: list[list[str]] = []

    class TrackingProbe:
        last_probe_errors: dict[str, str] = {}

        def probe(self, candidates: list[str]) -> dict[str, bool]:
            probed.append(list(candidates))
            return {c: True for c in candidates}

    ModelResolver(config, probe=TrackingProbe()).resolve("pro")
    assert probed == [["gemini-2.5-pro"]]
