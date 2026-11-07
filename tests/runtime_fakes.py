"""Offline Adapters shared by application contract tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from types import SimpleNamespace

import pytest


class NoAuditFactory:
    def usage_snapshot(self) -> tuple[str, dict[str, int | None]] | None:
        return None

    def persist_audit(self, runtime: dict[str, object] | None = None) -> None:
        pass


def install_fake_any_llm(
    monkeypatch: pytest.MonkeyPatch,
    respond: Callable[[str], str],
    *,
    calls: list[str],
    constructed: list[dict[str, object]],
    usage: tuple[int, int] = (10, 5),
) -> None:
    """Replace any-llm client construction with an offline streaming stand-in.

    ``respond`` maps the requested model ID to the reply text, or raises to simulate a
    transport failure. Each completion yields one text chunk, then a usage chunk.
    """
    from any_llm import AnyLLM

    class Client:
        def completion(self, **options: object) -> Iterator[SimpleNamespace]:
            model = str(options["model"])
            calls.append(model)
            text = respond(model)
            delta = SimpleNamespace(content=text)
            choice = SimpleNamespace(delta=delta, finish_reason="stop")
            yield SimpleNamespace(choices=[choice], usage=None)
            totals = SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1])
            yield SimpleNamespace(choices=[], usage=totals)

    def create(provider: str, **kwargs: object) -> Client:
        constructed.append({"provider": provider, **kwargs})
        return Client()

    monkeypatch.setattr(AnyLLM, "create", staticmethod(create))
