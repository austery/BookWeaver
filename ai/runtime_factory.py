"""Invocation-scoped authorization and concrete provider construction."""

from __future__ import annotations

import sys
import uuid
import json
import os
import tempfile
from pathlib import Path
from dataclasses import asdict, dataclass
from collections.abc import Callable, Sequence
from typing import Protocol

from ai.antigravity_provider import DEFAULT_TIMEOUT_SECONDS, AntigravityProvider
from ai.model_profiles import ResolvedModel, is_metered
from ai.ports.provider import (
    ITranslationProvider,
    OutputTruncatedError,
    ProviderAuthenticationError,
    ProviderUnavailableError,
    RateLimitError,
    TranslationError,
)


class PaidAuthorizationError(ValueError):
    """Metered execution was requested without invocation consent."""


@dataclass
class RequestUsage:
    model: str
    protocol: str
    provider: str
    state: str = "pending"
    input_tokens: int | None = None
    output_tokens: int | None = None


class IProviderFactory(Protocol):
    def create(
        self,
        model: ResolvedModel,
        *,
        protocol: str,
        config: dict[str, object],
        allow_paid_api: bool,
        remaining_chars: int,
    ) -> ITranslationProvider: ...

    def usage_snapshot(self) -> tuple[str, dict[str, int | None]] | None:
        """Return invocation usage, or None when this Adapter cannot report it."""
        ...

    def persist_audit(self, runtime: dict[str, object] | None = None) -> None:
        """Persist current invocation evidence, including on failed execution."""
        ...


_VENDOR_LABELS = {"gemini": "Gemini", "openai": "OpenAI", "anthropic": "Anthropic"}
_KEY_VARIABLES = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
DEFAULT_API_TIMEOUT_SECONDS = 600.0


def _translate_metered_error(exc: Exception) -> TranslationError:
    """Map an any-llm unified exception to the port vocabulary without echoing request text."""
    import any_llm

    if isinstance(exc, any_llm.AuthenticationError):
        return ProviderAuthenticationError(
            "Metered API rejected the credentials; no automatic retry was made"
        )
    if isinstance(exc, any_llm.RateLimitError):
        return RateLimitError("Metered API rate or credit limit reached; no automatic retry")
    return ProviderUnavailableError("Paid API request failed; no automatic retry was made")


class _MeteredProvider(ITranslationProvider):
    """One any-llm request per planned batch; vendor differences stay inside any-llm."""

    backend = "any_llm"

    def __init__(
        self,
        model: ResolvedModel,
        api_key: str,
        protocol: str,
        usage: list[RequestUsage],
        on_usage: Callable[[], None],
        *,
        timeout_seconds: float = DEFAULT_API_TIMEOUT_SECONDS,
        api_base: str | None = None,
    ) -> None:
        from any_llm import AnyLLM

        if model.output_cap is None:
            raise ValueError("Metered model has no pinned output cap")
        # api_base is a test seam for an offline local endpoint, not user configuration.
        self._client = AnyLLM.create(
            model.provider,
            api_key=api_key,
            api_base=api_base,
            unified_exceptions=True,
            max_retries=0,
        )
        self._model = model
        self._protocol = protocol
        self._usage = usage
        self._on_usage = on_usage
        self._timeout = timeout_seconds

    def translate_batch(self, segments: Sequence[str], *, system_prompt: str) -> list[str]:
        from ai.adapters.providers._delimiter import (
            augment_prompt_for_batch,
            join_segments,
            split_response,
        )

        if not segments:
            return []
        request_usage = RequestUsage(self._model.model_id, self._protocol, self._model.provider)
        self._usage.append(request_usage)
        self._on_usage()
        options: dict[str, object] = {
            "model": self._model.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": augment_prompt_for_batch(
                        system_prompt, len(segments), protocol=self._protocol
                    ),
                },
                {
                    "role": "user",
                    "content": join_segments(list(segments), protocol=self._protocol),
                },
            ],
            "max_tokens": self._model.output_cap,
            "stream": True,
            "stream_options": {"include_usage": True},
            "timeout": self._timeout,
        }
        if self._model.api_effort is not None:
            # Anthropic-native effort without enabling extended thinking (SPEC-024 §12).
            options["output_config"] = {"effort": self._model.api_effort}
        parts: list[str] = []
        finish_reason: str | None = None
        try:
            for chunk in self._client.completion(**options):
                for choice in chunk.choices:
                    if choice.delta.content:
                        parts.append(choice.delta.content)
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                if chunk.usage is not None:
                    request_usage.input_tokens = chunk.usage.prompt_tokens
                    request_usage.output_tokens = chunk.usage.completion_tokens
        except BaseException as exc:
            request_usage.state = "failed"
            try:
                self._on_usage()
            except Exception as audit_error:
                exc.add_note(f"Usage audit also failed: {type(audit_error).__name__}")
            if not isinstance(exc, Exception):
                raise
            raise _translate_metered_error(exc) from exc
        truncated = finish_reason == "length"
        request_usage.state = "truncated" if truncated else "responded"
        self._on_usage()
        if truncated:
            raise OutputTruncatedError(
                "Metered API output reached its token cap; lower --max-batch-chars and resume"
            )
        text = "".join(parts)
        if not text.strip():
            raise ProviderUnavailableError("Paid API returned empty output")
        return split_response(text, len(segments), protocol=self._protocol)


def _antigravity_timeout(config: dict[str, object]) -> float:
    """Per-batch Antigravity deadline from validated config, else the built-in default."""
    section = config.get("antigravity", {})
    value = section.get("timeout_seconds") if isinstance(section, dict) else None
    if value is None:
        return DEFAULT_TIMEOUT_SECONDS
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError("antigravity.timeout_seconds must be a positive number of seconds")
    return float(value)


def _api_timeout(config: dict[str, object]) -> float:
    """Per-request metered API deadline from validated config, else the default."""
    section = config.get("api", {})
    value = section.get("timeout_seconds") if isinstance(section, dict) else None
    if value is None:
        return DEFAULT_API_TIMEOUT_SECONDS
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError("api.timeout_seconds must be a positive number of seconds")
    return float(value)


class DefaultProviderFactory:
    """One instance is owned by one invocation, including its glossary work."""

    def __init__(self, *, audit_directory: Path | None = None) -> None:
        self._authorized = False
        self._usage: list[RequestUsage] = []
        self._run_id = str(uuid.uuid4())
        self._audit_directory = audit_directory
        self._runtime: dict[str, object] = {}

    def persist_audit(self, runtime: dict[str, object] | None = None) -> None:
        """Persist available per-request counts independently of translation checkpoints."""
        if runtime is not None:
            self._runtime = runtime
        if self._audit_directory is None:
            return
        self._audit_directory.mkdir(parents=True, exist_ok=True)
        usage = self.usage_snapshot()
        payload = {
            "run_id": self._run_id,
            "runtime": self._runtime,
            "requests": [asdict(request) for request in self._usage],
            "summary": usage[1] if usage is not None else None,
            "usage_scope": "metered_api_requests",
        }
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self._audit_directory, delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._audit_directory / f"{self._run_id}.json")
            descriptor = os.open(self._audit_directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def usage_snapshot(self) -> tuple[str, dict[str, int | None]] | None:
        provider = self._runtime.get("provider")
        if not isinstance(provider, str) or not is_metered(provider):
            return None
        counts: dict[str, int | None] = {"request_count": len(self._usage)}
        for key in ("input_tokens", "output_tokens"):
            values = [
                item.input_tokens if key == "input_tokens" else item.output_tokens
                for item in self._usage
            ]
            counts[key] = (
                sum(value for value in values if value is not None)
                if all(value is not None for value in values)
                else None
            )
        return self._run_id, counts

    def create(
        self,
        model: ResolvedModel,
        *,
        protocol: str,
        config: dict[str, object],
        allow_paid_api: bool,
        remaining_chars: int,
    ) -> ITranslationProvider:
        self._runtime = {
            "provider": model.provider,
            "model": model.model_id,
            "profile": model.profile,
            "effective_effort": model.effort,
        }
        if model.provider == "cli":
            if allow_paid_api:
                raise PaidAuthorizationError(
                    "--allow-paid-api requires a metered --provider (gemini, openai, or anthropic)"
                )
            return AntigravityProvider(
                model, protocol=protocol, timeout_seconds=_antigravity_timeout(config)
            )
        if not self._authorized:
            if not allow_paid_api:
                if not sys.stdin.isatty():
                    raise PaidAuthorizationError(
                        "Paid API requires --allow-paid-api when non-interactive"
                    )
                print(
                    f"Metered {_VENDOR_LABELS[model.provider]} API: {model.model_id}; remaining source approximately {remaining_chars} characters, including any requested glossary work. This invocation may incur charges."
                )
                if input("Type USE_API to continue: ") != "USE_API":
                    raise PaidAuthorizationError("Paid API execution was not authorized")
            self._authorized = True
        variable = _KEY_VARIABLES[model.provider]
        key = os.environ.get(variable)
        if not key and model.provider == "gemini":
            api = config.get("gemini_api", {})
            configured_key = api.get("api_key") if isinstance(api, dict) else None
            key = configured_key if isinstance(configured_key, str) else None
        if not key:
            source = f"{variable} or gemini_api.api_key" if model.provider == "gemini" else variable
            raise ValueError(f"{source} is required for paid API execution")
        return _MeteredProvider(
            model,
            key,
            protocol,
            self._usage,
            self.persist_audit,
            timeout_seconds=_api_timeout(config),
        )
