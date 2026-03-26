from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ai.gemini_provider import GeminiProvider

if TYPE_CHECKING:
    from ai.gemini_api_provider import GeminiAPIProvider


@dataclass
class ProviderPair:
    """Primary + optional fallback provider for a single translation run.

    Two fallback concepts are distinct:
    - Model-level fallback: handled by ModelResolver (tries next model if unavailable)
    - Provider-level fallback: handled here (tries API if CLI fails, same model)
    """

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
            raise ValueError(f"Unknown provider '{provider_name}'. Expected 'cli' or 'api'")

        if provider_name == "api" or cli_api_fallback_enabled:
            from ai.gemini_api_provider import GeminiAPIProvider

        if provider_name == "api":
            primary: GeminiProvider | GeminiAPIProvider = GeminiAPIProvider(  # type: ignore[assignment]
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
