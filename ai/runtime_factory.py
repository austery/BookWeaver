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

from ai.antigravity_provider import AntigravityProvider
from ai.model_profiles import ResolvedModel
from ai.ports.provider import ITranslationProvider, ProviderUnavailableError


class PaidAuthorizationError(ValueError):
    """Metered execution was requested without invocation consent."""


@dataclass
class RequestUsage:
    model: str
    protocol: str
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


class _PaidProvider(ITranslationProvider):
    def __init__(
        self,
        model: ResolvedModel,
        api_key: str | None,
        protocol: str,
        usage: list[RequestUsage],
        on_usage: Callable[[], None],
    ) -> None:
        from google import genai
        from google.genai import types

        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)),
        )
        self._model = model
        self._protocol = protocol
        self._usage = usage
        self._on_usage = on_usage

    def translate_batch(self, segments: Sequence[str], *, system_prompt: str) -> list[str]:
        from google.genai import types
        from ai.adapters.providers._delimiter import (
            augment_prompt_for_batch,
            join_segments,
            split_response,
        )

        if not segments:
            return []
        request_usage = RequestUsage(self._model.model_id, self._protocol)
        self._usage.append(request_usage)
        self._on_usage()
        try:
            response = self._client.models.generate_content(
                model=self._model.model_id,
                contents=join_segments(list(segments), protocol=self._protocol),
                config=types.GenerateContentConfig(
                    system_instruction=augment_prompt_for_batch(
                        system_prompt, len(segments), protocol=self._protocol
                    ),
                    http_options=types.HttpOptions(
                        timeout=600000, retry_options=types.HttpRetryOptions(attempts=1)
                    ),
                ),
            )
        except BaseException as exc:
            request_usage.state = "failed"
            self._on_usage()
            if not isinstance(exc, Exception):
                raise
            raise ProviderUnavailableError(
                "Paid API request failed; no automatic retry was made"
            ) from exc
        if response.usage_metadata is not None:
            request_usage.input_tokens = response.usage_metadata.prompt_token_count
            request_usage.output_tokens = response.usage_metadata.candidates_token_count
        request_usage.state = "responded"
        self._on_usage()
        if not response.text:
            raise ProviderUnavailableError("Paid API returned empty output")
        return split_response(response.text, len(segments), protocol=self._protocol)


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
        payload = {
            "run_id": self._run_id,
            "runtime": self._runtime,
            "requests": [asdict(request) for request in self._usage],
            "summary": self.usage_snapshot()[1],
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

    def usage_snapshot(self) -> tuple[str, dict[str, int | None]]:
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
                raise PaidAuthorizationError("--allow-paid-api requires --provider api")
            return AntigravityProvider(model, protocol=protocol)
        if not self._authorized:
            if not allow_paid_api:
                if not sys.stdin.isatty():
                    raise PaidAuthorizationError(
                        "Paid API requires --allow-paid-api when non-interactive"
                    )
                print(
                    f"Metered Gemini API: {model.model_id}; remaining source approximately {remaining_chars} characters, including any requested glossary work. This invocation may incur charges."
                )
                if input("Type USE_API to continue: ") != "USE_API":
                    raise PaidAuthorizationError("Paid API execution was not authorized")
            self._authorized = True
        api = config.get("gemini_api", {})
        configured_key = api.get("api_key") if isinstance(api, dict) else None
        key = os.environ.get("GEMINI_API_KEY") or (
            configured_key if isinstance(configured_key, str) else None
        )
        if not key:
            raise ValueError(
                "GEMINI_API_KEY or gemini_api.api_key is required for paid API execution"
            )
        return _PaidProvider(model, key, protocol, self._usage, self.persist_audit)
