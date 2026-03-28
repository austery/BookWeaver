from __future__ import annotations

import warnings
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai.model_probe import ModelProbe


class ModelRole(Enum):
    PRO = "pro"
    FLASH = "flash"
    LITE = "lite"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ResolvedModel:
    """Result of ModelResolver.resolve(): concrete model name + its logical role."""

    name: str
    role: ModelRole


class ModelResolver:
    """Resolves model aliases to concrete provider names + roles.

    Priority order:
      1. config.model_aliases (user-configured)
      2. Built-in alias table (_BUILTIN_ALIASES)
      3. Probe (if config.model_probe.enabled = true)
      4. Fallback chain (if config.enable_fallback = true)

    The probe is a subprocess-based availability check (ModelProbe) and has
    no dependency on Provider objects — no circular dependency risk.

    Usage:
        resolver = ModelResolver(config)
        result = resolver.resolve("pro")      # full resolution with probe
        result.name   # "gemini-2.5-pro"
        result.role   # ModelRole.PRO

        alias = resolver.resolve_alias("pro") # alias-only, no probe
    """

    _BUILTIN_ALIASES: dict[str, str] = {
        "pro": "gemini-2.5-pro",
        "flash": "gemini-2.5-flash",
        "lite": "gemini-2.5-flash-lite",
    }

    def __init__(self, config: dict, *, probe: ModelProbe | None = None) -> None:
        # Merge config aliases on top of builtins
        merged: dict[str, str] = dict(self._BUILTIN_ALIASES)
        aliases_raw = config.get("model_aliases")
        if isinstance(aliases_raw, dict):
            merged.update(
                {
                    k: v.strip()
                    for k, v in aliases_raw.items()
                    if isinstance(k, str) and isinstance(v, str) and v.strip()
                }
            )
        self._aliases = merged

        # Inverted map: concrete model name → role
        # When multiple aliases point to same model, alphabetically first alias key wins
        self._model_to_role: dict[str, ModelRole] = {}
        for key, model_name in sorted(self._aliases.items()):
            try:
                role = ModelRole(key)
            except ValueError:
                continue
            if model_name not in self._model_to_role:
                self._model_to_role[model_name] = role

        # Fallback chain (used when probe is active + enable_fallback=True)
        fallback_raw = config.get("fallback_chain")
        self._fallback_chain: list[str] = (
            [s for s in fallback_raw if isinstance(s, str) and s.strip()]
            if isinstance(fallback_raw, list)
            else []
        )
        self._enable_fallback: bool = bool(config.get("enable_fallback", False))

        # Probe: injected instance takes precedence (for testing), then config
        if probe is not None:
            self._probe: ModelProbe | None = probe
        else:
            probe_config = config.get("model_probe")
            probe_enabled = isinstance(probe_config, dict) and bool(
                probe_config.get("enabled", False)
            )
            if probe_enabled and isinstance(probe_config, dict):
                from ai.model_probe import ModelProbe

                ttl_raw = probe_config.get("cache_ttl_seconds", 3600)
                ttl = int(ttl_raw) if isinstance(ttl_raw, (int, float)) else 3600
                cache_path_raw = probe_config.get(
                    "cache_path", "~/.cache/bookweaver/model_probe_cache.json"
                )
                cache_path = Path(str(cache_path_raw)).expanduser()
                self._probe = ModelProbe(cache_path=cache_path, ttl_seconds=max(ttl, 0))
            else:
                self._probe = None

    def _walk_alias(self, requested: str) -> tuple[str, ModelRole]:
        """Walk alias chain → (concrete name, role). Detects cycles. Internal."""
        key = requested.strip()
        if not key:
            raise ValueError("requested model must be a non-empty string")

        visited: set[str] = set()
        matched_alias: str | None = None
        current = key

        while current in self._aliases:
            if current in visited:
                raise ValueError(f"Model alias cycle detected at '{current}'")
            visited.add(current)
            matched_alias = current
            current = self._aliases[current]

        if matched_alias is not None:
            try:
                role = ModelRole(matched_alias)
            except ValueError:
                role = ModelRole.UNKNOWN
        else:
            role = self._model_to_role.get(current, ModelRole.UNKNOWN)

        return current, role

    def resolve_alias(self, requested: str) -> ResolvedModel:
        """Alias-only resolution: no probe, no fallback chain.

        Use for logging or when you need the alias-resolved name without network calls.

        Raises:
            ValueError: alias cycle detected or empty input.
        """
        name, role = self._walk_alias(requested)
        return ResolvedModel(name=name, role=role)

    def resolve(self, requested: str) -> ResolvedModel:
        """Full resolution: alias → probe (if enabled) → fallback → ResolvedModel.

        If all probe candidates are unavailable, emits RuntimeWarning and returns
        the alias-resolved primary (never raises).

        Raises:
            ValueError: alias cycle detected or empty input.
        """
        primary_name, primary_role = self._walk_alias(requested)

        if self._probe is None:
            return ResolvedModel(name=primary_name, role=primary_role)

        # Build candidate list: primary first, then fallback chain (if enabled)
        candidates: list[tuple[str, ModelRole]] = [(primary_name, primary_role)]
        if self._enable_fallback:
            for fb in self._fallback_chain:
                fb_name, fb_role = self._walk_alias(fb)
                if fb_name not in {c[0] for c in candidates}:
                    candidates.append((fb_name, fb_role))

        names = [c[0] for c in candidates]
        availability = self._probe.probe(names)

        for name, role in candidates:
            if availability.get(name, False):
                return ResolvedModel(name=name, role=role)

        warnings.warn(
            f"All model candidates unavailable, using primary: {primary_name}",
            RuntimeWarning,
            stacklevel=2,
        )
        return ResolvedModel(name=primary_name, role=primary_role)
