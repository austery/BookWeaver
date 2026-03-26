# SPEC-011 ModelResolver & ProviderFactory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize model alias resolution and provider creation into two new modules (`ai/model_resolver.py`, `ai/provider_factory.py`), fixing the bug where `--model pro` in the EPUB pipeline resolves to the stale `gemini-3-pro-preview` instead of reading from `config.json`.

**Architecture:** `ModelResolver(config)` handles all alias → concrete model name + role resolution (reading from `config.model_aliases`, falling back to built-in aliases, optional probe/fallback). `ProviderFactory(config)` creates `ProviderPair(primary, fallback)` provider objects. Both existing pipelines (`03_translate_md.py`, `ai/epub_translate_roundtrip.py`) are refactored to use these modules.

**Tech Stack:** Python 3.13, `enum.Enum`, `dataclasses`, `ai/model_probe.py` (existing), `ai/gemini_provider.py` (existing), `ai/gemini_api_provider.py` (existing), `pytest`.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `ai/model_resolver.py` | `ModelRole` enum, `ResolvedModel` dataclass, `ModelResolver` class |
| **Create** | `ai/provider_factory.py` | `ProviderPair` dataclass, `ProviderFactory` class |
| **Create** | `tests/unit/test_model_resolver.py` | Unit tests for ModelResolver |
| **Create** | `tests/unit/test_provider_factory.py` | Unit tests for ProviderFactory |
| **Modify** | `03_translate_md.py` | Replace local `resolve_model_name` / `select_model_with_fallback` / `_create_model_probe` / `build_model_candidates` with delegation to `ModelResolver`; keep shim API for backward compat |
| **Modify** | `ai/epub_translate_roundtrip.py` | Remove `_MODEL_ALIASES` / `_resolve_model_name`; add `config` param; use `ModelResolver` + `ProviderFactory` |
| **Modify** | `09_epub_translate_roundtrip.py` | Pass `config=runtime_config` to `run_translate_roundtrip` |

---

## Task 1: Create `ai/model_resolver.py` (TDD)

**Files:**
- Create: `tests/unit/test_model_resolver.py`
- Create: `ai/model_resolver.py`

- [ ] **Step 1.1: Write failing tests**

Create `tests/unit/test_model_resolver.py`:

```python
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
```

- [ ] **Step 1.2: Run tests to verify they all fail**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
uv run pytest tests/unit/test_model_resolver.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'ai.model_resolver'`

- [ ] **Step 1.3: Implement `ai/model_resolver.py`**

Create `ai/model_resolver.py`:

```python
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
```

- [ ] **Step 1.4: Run tests to verify they all pass**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
uv run pytest tests/unit/test_model_resolver.py -v
```

Expected: all tests PASS.

- [ ] **Step 1.5: Run full test suite to check for regressions**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
uv run pytest -q
```

Expected: same number of tests passing as before (no regressions).

- [ ] **Step 1.6: Commit**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
git add ai/model_resolver.py tests/unit/test_model_resolver.py
git commit -m "feat(spec011): add ModelResolver with alias, role, probe and fallback support

- ModelRole enum: PRO / FLASH / LITE / UNKNOWN
- ResolvedModel(name, role) returned from resolve()
- config.model_aliases takes precedence over built-in aliases
- resolve_alias() for alias-only (no network); resolve() for full pipeline
- probe injectable for testing; reads config.model_probe in production
- alias cycle detection raises ValueError

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: Create `ai/provider_factory.py` (TDD)

**Files:**
- Create: `tests/unit/test_provider_factory.py`
- Create: `ai/provider_factory.py`

- [ ] **Step 2.1: Write failing tests**

Create `tests/unit/test_provider_factory.py`:

```python
from __future__ import annotations

import pytest

from ai.gemini_provider import GeminiProvider
from ai.provider_factory import ProviderFactory, ProviderPair


def test_cli_creates_gemini_provider_no_fallback() -> None:
    factory = ProviderFactory({})
    pair = factory.create("gemini-2.5-flash", provider_name="cli")
    assert isinstance(pair.primary, GeminiProvider)
    assert pair.primary.model == "gemini-2.5-flash"
    assert pair.fallback is None


def test_cli_with_fallback_creates_provider_pair() -> None:
    from ai.gemini_api_provider import GeminiAPIProvider

    factory = ProviderFactory({})
    pair = factory.create(
        "gemini-2.5-pro",
        provider_name="cli",
        api_key="test-key",
        cli_api_fallback_enabled=True,
    )
    assert isinstance(pair.primary, GeminiProvider)
    assert pair.primary.model == "gemini-2.5-pro"
    assert isinstance(pair.fallback, GeminiAPIProvider)
    assert pair.fallback.model == "gemini-2.5-pro"


def test_api_creates_gemini_api_provider_no_fallback() -> None:
    from ai.gemini_api_provider import GeminiAPIProvider

    factory = ProviderFactory({})
    pair = factory.create("gemini-2.5-flash", provider_name="api", api_key="test-key")
    assert isinstance(pair.primary, GeminiAPIProvider)
    assert pair.primary.model == "gemini-2.5-flash"
    assert pair.fallback is None


def test_invalid_provider_raises_value_error() -> None:
    factory = ProviderFactory({})
    with pytest.raises(ValueError, match="Unknown provider 'grpc'"):
        factory.create("gemini-2.5-flash", provider_name="grpc")


def test_cli_without_fallback_flag_has_no_fallback() -> None:
    factory = ProviderFactory({})
    pair = factory.create("gemini-2.5-flash", provider_name="cli", api_key="test-key")
    assert pair.fallback is None
```

- [ ] **Step 2.2: Run tests to verify they all fail**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
uv run pytest tests/unit/test_provider_factory.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'ai.provider_factory'`

- [ ] **Step 2.3: Implement `ai/provider_factory.py`**

Create `ai/provider_factory.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ai.gemini_provider import GeminiProvider

if TYPE_CHECKING:
    from ai.gemini_api_provider import GeminiAPIProvider


@dataclass
class ProviderPair:
    """Primary + optional fallback provider for a single translation run."""

    primary: GeminiProvider | GeminiAPIProvider
    fallback: GeminiAPIProvider | None


class ProviderFactory:
    """Creates GeminiProvider / GeminiAPIProvider pairs from a resolved model name.

    Usage:
        factory = ProviderFactory(config)
        pair = factory.create("gemini-2.5-pro", provider_name="cli",
                               api_key=..., cli_api_fallback_enabled=True)
        pair.primary   # GeminiProvider (CLI)
        pair.fallback  # GeminiAPIProvider or None

    Two fallback concepts are distinct:
    - Model-level fallback: handled by ModelResolver (tries next model if primary unavailable)
    - Provider-level fallback: handled here (tries API if CLI call fails, same model)
    """

    def __init__(self, config: dict) -> None:
        self._config = config

    def create(
        self,
        model: str,
        provider_name: str = "cli",
        api_key: str | None = None,
        cli_api_fallback_enabled: bool = False,
    ) -> ProviderPair:
        """Create primary + optional fallback provider.

        Args:
            model: Already-resolved concrete model name (e.g. "gemini-2.5-pro").
            provider_name: "cli" uses GeminiProvider; "api" uses GeminiAPIProvider.
            api_key: Required when provider_name="api" or cli_api_fallback_enabled=True.
            cli_api_fallback_enabled: When True with provider_name="cli", also creates
                a GeminiAPIProvider as fallback (same model, different transport).

        Returns:
            ProviderPair(primary, fallback)

        Raises:
            ValueError: provider_name is not "cli" or "api".
        """
        if provider_name not in ("cli", "api"):
            raise ValueError(
                f"Unknown provider '{provider_name}'. Expected 'cli' or 'api'"
            )

        if provider_name == "api" or cli_api_fallback_enabled:
            from ai.gemini_api_provider import GeminiAPIProvider

        if provider_name == "api":
            primary = GeminiAPIProvider(  # type: ignore[assignment]
                api_key=api_key, model=model, config=self._config
            )
            return ProviderPair(primary=primary, fallback=None)

        primary = GeminiProvider(model=model)
        fallback = None
        if cli_api_fallback_enabled:
            fallback = GeminiAPIProvider(  # type: ignore[assignment]
                api_key=api_key, model=model, config=self._config
            )
        return ProviderPair(primary=primary, fallback=fallback)
```

- [ ] **Step 2.4: Run tests to verify they all pass**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
uv run pytest tests/unit/test_provider_factory.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 2.5: Run full test suite**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
uv run pytest -q
```

Expected: no regressions.

- [ ] **Step 2.6: Commit**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
git add ai/provider_factory.py tests/unit/test_provider_factory.py
git commit -m "feat(spec011): add ProviderFactory creating ProviderPair (primary + fallback)

- ProviderPair(primary, fallback): separates provider-level fallback from
  model-level fallback (handled by ModelResolver)
- Supports cli / api provider_name; cli_api_fallback_enabled for CLI→API fallback
- config passed through to GeminiAPIProvider for api_key resolution

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: Refactor `03_translate_md.py`

**Files:**
- Modify: `03_translate_md.py` (lines ~182–280: local resolver functions)
- Tests pass unchanged (shim API preserved)

### Context

`03_translate_md.py` currently defines these functions inline:
- `resolve_model_name(requested, config)` → `str`
- `build_model_candidates(requested, config)` → `list[str]`
- `_create_model_probe(config)` → `ModelProbe | None`
- `select_model_with_fallback(requested, config, probe=None)` → `str`

These are used directly in `translate_files()` and `print_model_selection_preview()`.

Existing tests in `tests/unit/test_translate_step3_refactor.py` call these functions via `module.resolve_model_name(...)` and `module.select_model_with_fallback(...)`, so we keep the same signatures as **thin shims** delegating to `ModelResolver`.

- [ ] **Step 3.1: Add import and replace the four functions with shims**

In `03_translate_md.py`, find the block starting at line 182 (`def resolve_model_name`) through the end of `select_model_with_fallback` (~line 280). Replace the entire block with:

```python
from ai.model_resolver import ModelResolver, ResolvedModel  # noqa: E402 (after existing imports)
```

Add this import at the top of `03_translate_md.py` alongside the existing `from ai.model_probe import ModelProbe` import:

```python
from ai.model_resolver import ModelResolver, ResolvedModel
```

Then replace the four functions (lines ~182–280) with these shims:

```python
def resolve_model_name(requested_model: str, runtime_config: RuntimeConfig | None = None) -> str:
    """Shim: alias-only resolution. Use ModelResolver directly for new code."""
    return ModelResolver(runtime_config or {}).resolve_alias(requested_model).name


def build_model_candidates(
    requested_model: str, runtime_config: RuntimeConfig | None = None
) -> list[str]:
    """Shim: returns alias-resolved primary + fallback chain. Use ModelResolver for new code."""
    config = runtime_config or {}
    primary = ModelResolver(config).resolve_alias(requested_model).name
    candidates: list[str] = [primary]
    if bool(config.get("enable_fallback", True)):
        fallback_chain = config.get("fallback_chain")
        if isinstance(fallback_chain, list):
            resolver = ModelResolver(config)
            for raw_fallback in fallback_chain:
                if not isinstance(raw_fallback, str) or not raw_fallback.strip():
                    continue
                resolved_fallback = resolver.resolve_alias(raw_fallback).name
                if resolved_fallback not in candidates:
                    candidates.append(resolved_fallback)
    return candidates


def _create_model_probe(runtime_config: RuntimeConfig) -> ModelProbe | None:
    """Shim: kept for backward compat. ModelResolver creates probes internally."""
    probe_config_raw = runtime_config.get("model_probe")
    if not isinstance(probe_config_raw, dict):
        return None
    if not bool(probe_config_raw.get("enabled", True)):
        return None

    ttl_raw = probe_config_raw.get("cache_ttl_seconds", 3600)
    ttl_seconds = int(ttl_raw) if isinstance(ttl_raw, (int, float)) else 3600
    cache_path_raw = probe_config_raw.get(
        "cache_path", "~/.cache/bookweaver/model_probe_cache.json"
    )
    cache_path = Path(str(cache_path_raw)).expanduser()
    return ModelProbe(cache_path=cache_path, ttl_seconds=max(ttl_seconds, 0))


def select_model_with_fallback(
    requested_model: str,
    runtime_config: RuntimeConfig | None = None,
    probe: ModelProbe | None = None,
) -> str:
    """Shim: full resolution with probe/fallback. Use ModelResolver directly for new code."""
    return ModelResolver(runtime_config or {}, probe=probe).resolve(requested_model).name
```

- [ ] **Step 3.2: Update `translate_files` to use `ModelResolver` directly**

In `translate_files`, find the section that calls `select_model_with_fallback` (around line 472–500) and replace it.

**Find this block** (around line 471):
```python
        selected_model = forced_model
        if not selected_model:
            if selector is not None:
                selected_model = selector.select(len(content))
            else:
                selected_model = config.get("default_model", "gemini-2.5-flash")

        requested_model = selected_model
        try:
            selected_model = select_model_with_fallback(
                requested_model,
                config,
                probe=probe,
            )
        except Exception as e:
            print(f"    Error selecting model for {filename}: {e}")
            failed_count += 1
            append_progress_log(
                progress_log_path,
                filename=filename,
                status="failed_model_selection",
                elapsed_seconds=time.perf_counter() - file_start_time,
                message=str(e),
            )
            continue

        resolved_requested_model = resolve_model_name(requested_model, config)
        if resolved_requested_model != requested_model:
            print(f"    Model alias resolved: {requested_model} -> {resolved_requested_model}")
        if selected_model != resolved_requested_model:
            print(f"    Model fallback selected: {resolved_requested_model} -> {selected_model}")
        print(f"    Model: {selected_model}")
```

**Replace with:**
```python
        selected_model = forced_model
        if not selected_model:
            if selector is not None:
                selected_model = selector.select(len(content))
            else:
                selected_model = config.get("default_model", "gemini-2.5-flash")

        requested_model = selected_model
        try:
            resolved = resolver.resolve(requested_model)
            selected_model = resolved.name
        except Exception as e:
            print(f"    Error selecting model for {filename}: {e}")
            failed_count += 1
            append_progress_log(
                progress_log_path,
                filename=filename,
                status="failed_model_selection",
                elapsed_seconds=time.perf_counter() - file_start_time,
                message=str(e),
            )
            continue

        alias_resolved = resolver.resolve_alias(requested_model).name
        if alias_resolved != requested_model:
            print(f"    Model alias resolved: {requested_model} -> {alias_resolved}")
        if selected_model != alias_resolved:
            print(f"    Model fallback selected: {alias_resolved} -> {selected_model}")
        print(f"    Model: {selected_model}")
```

Also, **add `resolver` initialization** just before the file loop. Find the `probe` initialization and add `resolver` after it:

```python
    probe = _create_model_probe(config)
    resolver = ModelResolver(config, probe=probe)
```

- [ ] **Step 3.3: Update `print_model_selection_preview`**

Find `print_model_selection_preview` (around line 284) and replace its body:

```python
def print_model_selection_preview(requested_model: str, runtime_config: RuntimeConfig) -> None:
    """Print model resolution details without translating files."""
    resolver = ModelResolver(runtime_config)
    alias_result = resolver.resolve_alias(requested_model)
    full_result = resolver.resolve(requested_model)
    print("Model selection preview:")
    print(f"  Requested: {requested_model}")
    if alias_result.name != requested_model:
        print(f"  Alias resolved: {requested_model} -> {alias_result.name}")
    if full_result.name != alias_result.name:
        print(f"  Fallback selected: {alias_result.name} -> {full_result.name}")
    print(f"  Final selected model: {full_result.name}")
```

- [ ] **Step 3.4: Syntax check and run full tests**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
uv run python -m py_compile 03_translate_md.py && echo "OK"
uv run pytest -q
```

Expected: `OK` then all tests pass (including `test_translate_step3_refactor.py`).

- [ ] **Step 3.5: Commit**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
git add 03_translate_md.py
git commit -m "refactor(spec011): 03_translate_md uses ModelResolver; keeps shim API

- translate_files() creates ModelResolver(config) once before file loop
- resolve_model_name / select_model_with_fallback kept as backward-compat shims
- print_model_selection_preview rewritten using ModelResolver
- No behavior changes; all existing tests pass

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: Refactor `ai/epub_translate_roundtrip.py` + `09_epub_translate_roundtrip.py`

**Files:**
- Modify: `ai/epub_translate_roundtrip.py`
- Modify: `09_epub_translate_roundtrip.py`

### Context

`ai/epub_translate_roundtrip.py` currently:
1. Has `_MODEL_ALIASES = {"pro": "gemini-3-pro-preview", ...}` (hardcoded, ignores config)
2. Has `_resolve_model_name(model)` using `_MODEL_ALIASES`
3. Creates `primary_provider` and `fallback_api_provider` inline in `run_translate_roundtrip`
4. Checks `is_pro_model = resolved_model == _MODEL_ALIASES["pro"]` for timeout/prebatch
5. `run_translate_roundtrip` has no `config` parameter

`09_epub_translate_roundtrip.py` already calls `load_runtime_config()` but does not pass it to `run_translate_roundtrip`.

- [ ] **Step 4.1: Add `config` parameter to `run_translate_roundtrip`**

In `ai/epub_translate_roundtrip.py`, find the `run_translate_roundtrip` function signature and add `config`:

**Find:**
```python
def run_translate_roundtrip(
    *,
    source_epub: Path,
    output_epub: Path,
    output_lang: str,
    bilingual_style: str,
    model: str,
    provider_name: str = "cli",
    api_key: str | None = None,
```

**Replace with:**
```python
def run_translate_roundtrip(
    *,
    source_epub: Path,
    output_epub: Path,
    output_lang: str,
    bilingual_style: str,
    model: str,
    config: dict | None = None,
    provider_name: str = "cli",
    api_key: str | None = None,
```

- [ ] **Step 4.2: Remove `_MODEL_ALIASES` and `_resolve_model_name`**

In `ai/epub_translate_roundtrip.py`, find and **delete** the following block (around lines 36–43):

```python
# _MODEL_ALIASES is independent from the config.json alias table loaded by
# load_runtime_config(). This local table maps short CLI names to full EPUB
# workflow model identifiers and is not affected by user config overrides.
_MODEL_ALIASES = {
    "pro": "gemini-3-pro-preview",
    "flash": "gemini-2.5-flash",
    "lite": "gemini-2.5-flash-lite",
}
```

Also **delete** the `_resolve_model_name` function (around lines 133–138):

```python
def _resolve_model_name(model: str) -> str:
    resolved = _MODEL_ALIASES.get(model.strip(), model.strip())
    if not resolved:
        raise ValueError("model must be a non-empty string")
    return resolved
```

- [ ] **Step 4.3: Add imports and replace alias/provider logic in `run_translate_roundtrip`**

Add these imports at the top of `ai/epub_translate_roundtrip.py` (alongside the existing `from ai.gemini_provider import GeminiProvider` import):

```python
from ai.model_resolver import ModelResolver, ModelRole
from ai.provider_factory import ProviderFactory
```

In `run_translate_roundtrip`, find the block that creates `resolved_model` and the providers (around line 683):

**Find:**
```python
    resolved_model = _resolve_model_name(model)
    package_model = load_epub_package(source_epub)

    # Lazy import GeminiAPIProvider only when actually needed (API provider or CLI with fallback)
    if provider_name == "api" or (provider_name == "cli" and cli_api_fallback_enabled):
        from ai.gemini_api_provider import GeminiAPIProvider

    primary_provider: GeminiProvider | "GeminiAPIProvider"
    if provider_name == "api":
        primary_provider = GeminiAPIProvider(
            api_key=api_key,
            model=resolved_model,
        )
    else:
        primary_provider = GeminiProvider(model=resolved_model)

    fallback_api_provider: "GeminiAPIProvider | None" = None
    use_fallback_api = False
    if provider_name == "cli" and cli_api_fallback_enabled:
        fallback_api_provider = GeminiAPIProvider(api_key=api_key, model=resolved_model)
```

**Replace with:**
```python
    _config = config or {}
    resolver = ModelResolver(_config)
    resolved = resolver.resolve(model)
    resolved_model = resolved.name
    is_pro_model = resolved.role == ModelRole.PRO

    package_model = load_epub_package(source_epub)

    factory = ProviderFactory(_config)
    provider_pair = factory.create(
        resolved_model,
        provider_name=provider_name,
        api_key=api_key,
        cli_api_fallback_enabled=cli_api_fallback_enabled,
    )
    primary_provider = provider_pair.primary
    fallback_api_provider = provider_pair.fallback
    use_fallback_api = False
```

- [ ] **Step 4.4: Remove the stale `is_pro_model` assignment**

The original code has `is_pro_model = resolved_model == _MODEL_ALIASES["pro"]` at around line 810 (inside the inner batch translation loop). Find and **delete** that line:

```python
            is_pro_model = resolved_model == _MODEL_ALIASES["pro"]
```

`is_pro_model` is now set correctly in Step 4.3 and no longer needs to be reassigned.

- [ ] **Step 4.5: Update `09_epub_translate_roundtrip.py` to pass config**

In `09_epub_translate_roundtrip.py`, find the `run_translate_roundtrip` call:

**Find:**
```python
    result = run_translate_roundtrip(
        source_epub=source_epub,
        output_epub=output_epub,
        output_lang=args.output_lang,
        bilingual_style=args.bilingual_style,
        model=args.model,
        provider_name=args.provider,
        api_key=api_key,
        custom_prompt=args.prompt,
        checkpoint_dir=checkpoint_dir,
        force_resume=args.force_resume,
        **resilience_overrides,
    )
```

**Replace with:**
```python
    result = run_translate_roundtrip(
        source_epub=source_epub,
        output_epub=output_epub,
        output_lang=args.output_lang,
        bilingual_style=args.bilingual_style,
        model=args.model,
        config=runtime_config,
        provider_name=args.provider,
        api_key=api_key,
        custom_prompt=args.prompt,
        checkpoint_dir=checkpoint_dir,
        force_resume=args.force_resume,
        **resilience_overrides,
    )
```

- [ ] **Step 4.6: Syntax check both files**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
uv run python -m py_compile ai/epub_translate_roundtrip.py && echo "epub OK"
uv run python -m py_compile 09_epub_translate_roundtrip.py && echo "09 OK"
```

Expected: `epub OK` then `09 OK`.

- [ ] **Step 4.7: Run full test suite**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
uv run pytest -q
```

Expected: all tests pass. Key tests to watch:
- `tests/unit/test_epub_translate_roundtrip.py::test_translate_roundtrip_prebatches_pro_requests_before_retry` — uses `model="pro"`, must still trigger pro pre-batch behavior via `ModelRole.PRO`
- `tests/unit/test_epub_translate_roundtrip.py::test_translate_roundtrip_flash_keeps_single_doc_batch` — `model="flash"` must not trigger pro batching

- [ ] **Step 4.8: Run linter**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
uv run ruff check ai/epub_translate_roundtrip.py ai/model_resolver.py ai/provider_factory.py 09_epub_translate_roundtrip.py 03_translate_md.py
uv run ruff format --check ai/epub_translate_roundtrip.py ai/model_resolver.py ai/provider_factory.py
```

Fix any issues reported, then re-run until clean.

- [ ] **Step 4.9: Commit**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
git add ai/epub_translate_roundtrip.py 09_epub_translate_roundtrip.py
git commit -m "fix(spec011): EPUB pipeline uses ModelResolver + ProviderFactory

- Remove _MODEL_ALIASES (was hardcoded 'pro' → gemini-3-pro-preview, ignoring config)
- run_translate_roundtrip() now accepts config param, passes to ModelResolver
- is_pro_model now from resolved.role == ModelRole.PRO (not string comparison)
- ProviderFactory creates primary + fallback provider pair
- 09_epub_translate_roundtrip.py passes runtime_config to run_translate_roundtrip
- '--model pro' now correctly resolves to config.model_aliases['pro'] = gemini-2.5-pro

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec Requirement | Task |
|-----------------|------|
| `ModelResolver` class with `resolve()` | Task 1 |
| `ModelRole` enum (PRO/FLASH/LITE/UNKNOWN) | Task 1 |
| `ResolvedModel(name, role)` — role in forward pass, not reverse-lookup | Task 1 |
| `resolve_alias()` for alias-only (no probe) | Task 1 |
| probe injectable for testing | Task 1 |
| Config `model_aliases` takes precedence over built-ins | Task 1 |
| Probe/fallback reads from config, disabled by default | Task 1 |
| `ProviderFactory.create()` → `ProviderPair(primary, fallback)` | Task 2 |
| `provider_name` validation + `ValueError` | Task 2 |
| `03_translate_md.py` refactored, shim API preserved | Task 3 |
| `epub_translate_roundtrip.py`: remove `_MODEL_ALIASES` + `_resolve_model_name` | Task 4 |
| `run_translate_roundtrip` accepts `config` param | Task 4 |
| `is_pro_model` uses `resolved.role == ModelRole.PRO` | Task 4 |
| `09_epub_translate_roundtrip.py` passes config | Task 4 |
| All existing tests pass | Tasks 1–4 |

### Type Consistency

- `ModelResolver.resolve()` → `ResolvedModel` ✅ (used as `resolved.name`, `resolved.role` in Tasks 3 + 4)
- `ModelResolver.resolve_alias()` → `ResolvedModel` ✅ (same type as `resolve()`)
- `ProviderFactory.create()` → `ProviderPair` ✅
- `ProviderPair.primary` → `GeminiProvider | GeminiAPIProvider` ✅
- `ProviderPair.fallback` → `GeminiAPIProvider | None` ✅
- `ModelResolver.__init__(config, *, probe=None)` — `probe` used in Task 3 shim (`select_model_with_fallback`) ✅
