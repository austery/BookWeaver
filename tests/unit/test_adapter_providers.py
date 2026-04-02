"""Unit tests for the provider adapter layer.

Tests delimiter join/split logic and adapter retry/error-mapping behavior.
Uses fake raw providers — no real API calls or subprocess invocations.
"""

from __future__ import annotations

import pytest

from ai.adapters.providers._delimiter import (
    SEPARATOR_OVERHEAD,
    augment_prompt_for_batch,
    join_segments,
    split_response,
)
from ai.adapters.providers.gemini_cli_adapter import GeminiCLIAdapter
from ai.adapters.providers.gemini_api_adapter import GeminiAPIAdapter
from ai.ports.provider import RateLimitError, TranslationError


# ── Delimiter helpers ─────────────────────────────────────────


class TestJoinSegments:
    def test_empty(self) -> None:
        assert join_segments([]) == ""

    def test_single(self) -> None:
        assert join_segments(["Hello"]) == "Hello"

    def test_multiple(self) -> None:
        assert join_segments(["A", "B"]) == "A\n\n%%\n\nB"

    def test_three(self) -> None:
        assert join_segments(["X", "Y", "Z"]) == "X\n\n%%\n\nY\n\n%%\n\nZ"


class TestSplitResponse:
    def test_single_returns_stripped(self) -> None:
        assert split_response("  hello  ", 1) == ["hello"]

    def test_exact_separator(self) -> None:
        assert split_response("甲\n\n%%\n\n乙", 2) == ["甲", "乙"]

    def test_flexible_whitespace(self) -> None:
        assert split_response("A\n %%  \nB", 2) == ["A", "B"]

    def test_mismatch_raises(self) -> None:
        with pytest.raises(TranslationError, match="count mismatch"):
            split_response("only-one", 2)

    def test_zero_expected(self) -> None:
        assert split_response("anything", 0) == []

    def test_three_segments(self) -> None:
        text = "一\n\n%%\n\n二\n\n%%\n\n三"
        assert split_response(text, 3) == ["一", "二", "三"]

    def test_empty_output_single_segment_raises(self) -> None:
        """Empty provider output must raise TranslationError, not return ['']."""
        with pytest.raises(TranslationError, match="empty"):
            split_response("", 1)

    def test_whitespace_only_output_single_segment_raises(self) -> None:
        """Whitespace-only output is also empty — must raise TranslationError."""
        with pytest.raises(TranslationError, match="empty"):
            split_response("   \n  ", 1)


class TestAugmentPrompt:
    def test_single_segment_unchanged(self) -> None:
        assert augment_prompt_for_batch("prompt", 1) == "prompt"

    def test_multi_segment_adds_instructions(self) -> None:
        result = augment_prompt_for_batch("prompt", 2)
        assert "%%" in result
        assert "IMPORTANT" in result

    def test_zero_segments_unchanged(self) -> None:
        assert augment_prompt_for_batch("prompt", 0) == "prompt"


class TestSeparatorOverhead:
    def test_is_six(self) -> None:
        assert SEPARATOR_OVERHEAD == 6


# ── Fake providers for testing ────────────────────────────────


class _FakeRateLimitError(RuntimeError):
    """Mimics ai.gemini_provider.RateLimitError."""

    __qualname__ = "RateLimitError"

    def __init__(self, msg: str = "429") -> None:
        super().__init__(msg)


# Fix type().__name__ check
_FakeRateLimitError.__name__ = "RateLimitError"


class _FakeTransientCLIError(RuntimeError):
    """Mimics ai.gemini_provider.TransientCLIError."""

    __qualname__ = "TransientCLIError"

    def __init__(self, msg: str = "AbortError") -> None:
        super().__init__(msg)


_FakeTransientCLIError.__name__ = "TransientCLIError"


class FakeRawProvider:
    """Fake raw translator matching GeminiProvider.translate_chunk interface."""

    def __init__(
        self,
        responses: list[str] | None = None,
        errors: list[Exception] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.errors = list(errors or [])
        self.calls: list[tuple[str, str]] = []

    def translate_chunk(
        self,
        text: str = "",
        chunk_size: int = 0,
        system_prompt: str = "",
        timeout_seconds: int = 180,
    ) -> str:
        self.calls.append((text, system_prompt))
        if self.errors:
            raise self.errors.pop(0)
        if self.responses:
            return self.responses.pop(0)
        # Echo with prefix (default)
        return "翻译:" + text


# ── GeminiCLIAdapter tests ────────────────────────────────────


class TestGeminiCLIAdapterHappyPath:
    def test_single_segment(self) -> None:
        raw = FakeRawProvider(responses=["你好"])
        adapter = GeminiCLIAdapter(raw)

        result = adapter.translate_batch(["Hello"], system_prompt="Translate.")

        assert result == ["你好"]
        assert len(raw.calls) == 1

    def test_multiple_segments(self) -> None:
        raw = FakeRawProvider(responses=["甲\n\n%%\n\n乙"])
        adapter = GeminiCLIAdapter(raw)

        result = adapter.translate_batch(["A", "B"], system_prompt="Translate.")

        assert result == ["甲", "乙"]
        # Input should be joined with %%
        assert "%%" in raw.calls[0][0]

    def test_empty_segments(self) -> None:
        raw = FakeRawProvider()
        adapter = GeminiCLIAdapter(raw)

        result = adapter.translate_batch([], system_prompt="Translate.")

        assert result == []
        assert len(raw.calls) == 0

    def test_system_prompt_augmented_for_batch(self) -> None:
        raw = FakeRawProvider(responses=["X\n\n%%\n\nY"])
        adapter = GeminiCLIAdapter(raw)

        adapter.translate_batch(["A", "B"], system_prompt="Base prompt.")

        sent_prompt = raw.calls[0][1]
        assert "Base prompt." in sent_prompt
        assert "%%" in sent_prompt  # augmented with batch instructions

    def test_system_prompt_not_augmented_for_single(self) -> None:
        raw = FakeRawProvider(responses=["翻译"])
        adapter = GeminiCLIAdapter(raw)

        adapter.translate_batch(["A"], system_prompt="Base prompt.")

        sent_prompt = raw.calls[0][1]
        assert sent_prompt == "Base prompt."


class TestGeminiCLIAdapterRetry:
    def test_rate_limit_retry_succeeds(self) -> None:
        sleeps: list[float] = []
        raw = FakeRawProvider(
            errors=[_FakeRateLimitError()],
            responses=["ok"],
        )
        adapter = GeminiCLIAdapter(
            raw,
            rate_limit_backoff=(10, 20),
            sleep_fn=sleeps.append,
        )

        result = adapter.translate_batch(["Hi"], system_prompt="T")

        assert result == ["ok"]
        assert sleeps == [10]
        assert len(raw.calls) == 2

    def test_rate_limit_exhausted_raises(self) -> None:
        raw = FakeRawProvider(
            errors=[_FakeRateLimitError(), _FakeRateLimitError()],
        )
        adapter = GeminiCLIAdapter(
            raw,
            rate_limit_backoff=(5,),  # only 1 retry
            sleep_fn=lambda _: None,
        )

        with pytest.raises(RateLimitError):
            adapter.translate_batch(["Hi"], system_prompt="T")

    def test_transient_retry_succeeds(self) -> None:
        sleeps: list[float] = []
        raw = FakeRawProvider(
            errors=[_FakeTransientCLIError()],
            responses=["ok"],
        )
        adapter = GeminiCLIAdapter(
            raw,
            transient_backoff=(30,),
            sleep_fn=sleeps.append,
        )

        result = adapter.translate_batch(["Hi"], system_prompt="T")

        assert result == ["ok"]
        assert sleeps == [30]

    def test_transient_multi_retry_succeeds_with_configured_sequence(self) -> None:
        sleeps: list[float] = []
        raw = FakeRawProvider(
            errors=[
                _FakeTransientCLIError("AbortError #1"),
                _FakeTransientCLIError("AbortError #2"),
            ],
            responses=["ok"],
        )
        adapter = GeminiCLIAdapter(
            raw,
            transient_backoff=(7, 11),
            sleep_fn=sleeps.append,
        )

        result = adapter.translate_batch(["Hi"], system_prompt="T")

        assert result == ["ok"]
        assert sleeps == [7, 11]
        assert len(raw.calls) == 3

    def test_transient_exhausted_raises(self) -> None:
        first = _FakeTransientCLIError("AbortError #1")
        second = _FakeTransientCLIError("AbortError #2")
        raw = FakeRawProvider(
            errors=[first, second],
        )
        adapter = GeminiCLIAdapter(
            raw,
            transient_backoff=(5,),  # only 1 retry
            sleep_fn=lambda _: None,
        )

        with pytest.raises(
            TranslationError,
            match=r"Transient CLI retries exhausted after 2 attempts \(configured retries: 1\)",
        ) as exc_info:
            adapter.translate_batch(["Hi"], system_prompt="T")
        assert exc_info.value.__cause__ is second

    def test_unknown_error_raises_immediately(self) -> None:
        raw = FakeRawProvider(errors=[ValueError("bad input")])
        adapter = GeminiCLIAdapter(raw, sleep_fn=lambda _: None)

        with pytest.raises(TranslationError, match="bad input"):
            adapter.translate_batch(["Hi"], system_prompt="T")


class TestGeminiCLIAdapterBackoffValidation:
    def test_rejects_bool_in_rate_limit_backoff(self) -> None:
        raw = FakeRawProvider()
        with pytest.raises(ValueError, match="rate_limit_backoff"):
            GeminiCLIAdapter(raw, rate_limit_backoff=(True, 5))

    def test_rejects_bool_in_transient_backoff(self) -> None:
        raw = FakeRawProvider()
        with pytest.raises(ValueError, match="transient_backoff"):
            GeminiCLIAdapter(raw, transient_backoff=(3, False))


class TestGeminiCLIAdapterCountMismatch:
    def test_count_mismatch_raises_translation_error(self) -> None:
        """Provider returns wrong segment count → TranslationError."""
        raw = FakeRawProvider(responses=["just-one-segment"])
        adapter = GeminiCLIAdapter(raw)

        with pytest.raises(TranslationError, match="count mismatch"):
            adapter.translate_batch(["A", "B"], system_prompt="T")


# ── GeminiAPIAdapter tests ────────────────────────────────────


class TestGeminiAPIAdapterHappyPath:
    def test_single_segment(self) -> None:
        raw = FakeRawProvider(responses=["你好"])
        adapter = GeminiAPIAdapter(raw)

        result = adapter.translate_batch(["Hello"], system_prompt="Translate.")

        assert result == ["你好"]

    def test_multiple_segments(self) -> None:
        raw = FakeRawProvider(responses=["甲\n\n%%\n\n乙"])
        adapter = GeminiAPIAdapter(raw)

        result = adapter.translate_batch(["A", "B"], system_prompt="Translate.")

        assert result == ["甲", "乙"]

    def test_empty(self) -> None:
        raw = FakeRawProvider()
        adapter = GeminiAPIAdapter(raw)
        assert adapter.translate_batch([], system_prompt="T") == []


class TestGeminiAPIAdapterErrors:
    def test_rate_limit_mapped(self) -> None:
        raw = FakeRawProvider(errors=[_FakeRateLimitError()])
        adapter = GeminiAPIAdapter(raw)

        with pytest.raises(RateLimitError):
            adapter.translate_batch(["Hi"], system_prompt="T")

    def test_generic_error_mapped(self) -> None:
        raw = FakeRawProvider(errors=[RuntimeError("server down")])
        adapter = GeminiAPIAdapter(raw)

        with pytest.raises(TranslationError, match="server down"):
            adapter.translate_batch(["Hi"], system_prompt="T")
