"""Version-pinned model selection; update concrete mappings here when upgrading."""

from dataclasses import dataclass
from typing import Literal

ModelProfile = Literal["flash", "pro"]
Effort = Literal["low", "medium", "high"]
ProviderName = Literal["cli", "gemini", "openai", "anthropic"]
# Owner policy for a row (SPEC-025 §3.8): default, manual (paid), or experiment (not qualified).
RowStatus = Literal["default", "manual", "experiment"]
# Highest proven evidence layer (SPEC-025 §3.8): 1 legal, 2 executable, 3 qualified.
EvidenceLayer = Literal[1, 2, 3]
CliRuntime = Literal["antigravity"]
METERED_PROVIDERS = frozenset({"gemini", "openai", "anthropic"})


@dataclass(frozen=True)
class _CliRow:
    """One owner-enabled subscription CLI combination (SPEC-025 §3.8)."""

    runtime: CliRuntime
    profile: ModelProfile
    family: str
    effort: Effort
    status: RowStatus
    layer: EvidenceLayer
    evidence: str


# Named rows, not the Cartesian product: anything absent here is rejected before a run.
# The family is the runtime's model family; effort is passed once through ``--effort``.
_CLI_ROWS: tuple[_CliRow, ...] = (
    _CliRow(
        "antigravity",
        "flash",
        "gemini-3.8-flash",
        "low",
        "default",
        2,
        "agy 1.5.3 probe 2026-11-07; one validated book on agy 1.1.27",
    ),
    _CliRow(
        "antigravity",
        "flash",
        "gemini-3.8-flash",
        "medium",
        "experiment",
        1,
        "effort comparison only; probed automatically on first use",
    ),
    _CliRow(
        "antigravity",
        "flash",
        "gemini-3.8-flash",
        "high",
        "experiment",
        1,
        "effort comparison only; probed automatically on first use",
    ),
    _CliRow(
        "antigravity",
        "pro",
        "gemini-4-argon",
        "low",
        "experiment",
        2,
        "agy 1.5.3 probe 2026-11-07 (segment_tags and delimiter)",
    ),
    _CliRow(
        "antigravity",
        "pro",
        "gemini-4-argon",
        "high",
        "experiment",
        1,
        "agy 1.5.3 roster 2026-11-07; probed automatically on first use",
    ),
)


def cli_model_id(family: str, effort: str) -> str:
    """Concrete roster ID for provenance; agy 1.5.3 lists models as ``<family>-<effort>``."""
    return f"{family}-{effort}"


def _validate_rows(rows: tuple[_CliRow, ...]) -> None:
    """Layer 1 check at import: one row per selection, and a known default."""
    keys = [(row.runtime, row.profile, row.effort) for row in rows]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise RuntimeError(f"Duplicate CLI rows in ai/model_profiles.py: {duplicates}")
    if ("antigravity", "flash", "low") not in keys:
        raise RuntimeError("The default antigravity flash/low row is missing")


# Seed certifications per (agy version, concrete model): pairs with recorded probe evidence.
# Any other pair is probed automatically before its first book batch (SPEC-025 §3.3).
CERTIFIED_AGY_MODELS = frozenset(
    {
        ("1.1.27", "gemini-3.8-flash-low"),
        ("1.5.3", "gemini-3.8-flash-low"),
        ("1.5.3", "gemini-4-argon-low"),
    }
)


def _validate_seeds(rows: tuple[_CliRow, ...], seeds: frozenset[tuple[str, str]]) -> None:
    """Every seeded model must belong to an enabled row; a dead seed hides a registry edit."""
    known = {cli_model_id(row.family, row.effort) for row in rows}
    dead = sorted(model for _, model in seeds if model not in known)
    if dead:
        raise RuntimeError(f"CERTIFIED_AGY_MODELS names models without a row: {dead}")


_validate_rows(_CLI_ROWS)
_validate_seeds(_CLI_ROWS, CERTIFIED_AGY_MODELS)


@dataclass(frozen=True)
class _MeteredEntry:
    model_id: str
    output_cap: int
    api_effort: str | None


# Metered API models (SPEC-024 §6.2). Each row cites its vendor source and read date;
# a provider without a row fails before any request instead of guessing a model.
_API_MODELS: dict[tuple[ProviderName, ModelProfile], _MeteredEntry] = {
    # Output cap 65,536 as listed in LiteLLM 1.108.2's model map, inspected 2026-11-07;
    # not yet checked against ai.google.dev, which was unreachable from that environment.
    ("gemini", "flash"): _MeteredEntry("gemini-2.5-flash", 65_536, None),
    ("gemini", "pro"): _MeteredEntry("gemini-2.5-pro", 65_536, None),
    # platform.claude.com models overview, read 2026-11-07: max output 128K tokens.
    ("anthropic", "flash"): _MeteredEntry("claude-sonnet-5-5", 128_000, "low"),
    ("anthropic", "pro"): _MeteredEntry("claude-opus-5-5", 128_000, "low"),
    # OpenAI: unfilled until its model documentation can be cited (SPEC-024 §11 Phase 3).
}


@dataclass(frozen=True)
class Row:
    """One named, owner-enabled selection shown to users (SPEC-026 §2.2).

    A row fixes provider, tier and effort; ``--row`` and the local API resolve it to the
    same selection the separate flags produce.
    """

    name: str
    provider: ProviderName
    profile: ModelProfile
    effort: Effort | None
    model_id: str
    status: RowStatus
    layer: EvidenceLayer | None
    evidence: str


# Short runtime names used in row names; one per CliRuntime.
_RUNTIME_PREFIX: dict[CliRuntime, str] = {"antigravity": "agy"}


def enabled_rows() -> tuple[Row, ...]:
    """Every selection a run may use, subscription CLI rows first, the default row first."""
    cli = sorted(_CLI_ROWS, key=lambda row: row.status != "default")
    rows = [
        Row(
            f"{_RUNTIME_PREFIX[row.runtime]}-{row.profile}-{row.effort}",
            "cli",
            row.profile,
            row.effort,
            cli_model_id(row.family, row.effort),
            row.status,
            row.layer,
            row.evidence,
        )
        for row in cli
    ]
    rows += [
        # Metered rows are paid and run only with --allow-paid-api; effort is vendor-pinned.
        Row(f"{provider}-{profile}", provider, profile, None, entry.model_id, "manual", None, "")
        for (provider, profile), entry in _API_MODELS.items()
        if is_metered(provider)
    ]
    return tuple(rows)


def find_row(name: str) -> Row:
    """The enabled row with this name; unknown names fail with the enabled list."""
    rows = enabled_rows()
    for row in rows:
        if row.name == name:
            return row
    raise ValueError(f"Unknown row {name!r}; enabled rows: {', '.join(r.name for r in rows)}")


@dataclass(frozen=True)
class ResolvedModel:
    profile: ModelProfile
    provider: ProviderName
    model_id: str
    effort: Effort | None
    # Metered providers only: requested output cap and vendor-pinned effort.
    output_cap: int | None = None
    api_effort: str | None = None
    # Subscription CLI only: the family passed to the runtime with ``--effort``.
    family: str | None = None
    status: RowStatus = "manual"


def is_metered(provider: str) -> bool:
    """True for providers that bill per request and require invocation consent."""
    return provider in METERED_PROVIDERS


def resolve_profile(
    profile: str = "flash", *, effort: str | None = None, provider: str = "cli"
) -> ResolvedModel:
    """Freeze a valid logical selection without discovery or silent fallback."""
    if profile not in ("flash", "pro"):
        raise ValueError(
            "Model profile must be flash or pro; concrete model names are not accepted"
        )
    if provider == "api":
        raise ValueError("Provider api was renamed; use gemini")
    if provider != "cli" and not is_metered(provider):
        raise ValueError("Provider must be cli, gemini, openai, or anthropic")
    if is_metered(provider):
        if effort is not None:
            raise ValueError("Explicit effort is not supported for metered API providers")
        entry = _API_MODELS.get((provider, profile))
        if entry is None:
            raise ValueError(
                f"No pinned {provider} model for profile {profile}; "
                "update ai/model_profiles.py with cited limits"
            )
        return ResolvedModel(
            profile, provider, entry.model_id, None, entry.output_cap, entry.api_effort
        )
    effective = effort if effort is not None else "low"
    if effective not in ("low", "medium", "high"):
        raise ValueError("effort must be low, medium, or high")
    for row in _CLI_ROWS:
        if (row.profile, row.effort) == (profile, effective):
            return ResolvedModel(
                profile,
                provider,
                cli_model_id(row.family, row.effort),
                row.effort,
                family=row.family,
                status=row.status,
            )
    enabled = ", ".join(f"{row.profile}/{row.effort}" for row in _CLI_ROWS)
    raise ValueError(
        f"Unsupported model/effort combination: {profile}/{effective}; enabled rows: {enabled}"
    )
