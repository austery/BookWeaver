"""Unit tests for ai.core.engine.TranslationEngine.

Uses mock implementations of ITranslationProvider and IBookSource.
Tests the orchestration logic (pipeline flow, batching coordination,
split-retry resilience) without touching real APIs or file formats.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from ai.core.engine import EngineConfig, TranslationEngine
from ai.ports.provider import ITranslationProvider, TranslationError
from ai.ports.source import IBookSource, Segment, TranslatedSegment


# ── Test Doubles ──────────────────────────────────────────────


class FakeProvider(ITranslationProvider):
    """Echoes segments with a prefix. Records all calls."""

    def __init__(self, prefix: str = "翻译:") -> None:
        self.prefix = prefix
        self.calls: list[tuple[list[str], str]] = []

    def translate_batch(
        self,
        segments: Sequence[str],
        *,
        system_prompt: str,
    ) -> list[str]:
        seg_list = list(segments)
        self.calls.append((seg_list, system_prompt))
        return [f"{self.prefix}{s}" for s in seg_list]


class FailThenSucceedProvider(ITranslationProvider):
    """Fails the first N calls, then delegates to a FakeProvider."""

    def __init__(self, fail_count: int = 1, prefix: str = "翻译:") -> None:
        self._fail_remaining = fail_count
        self._delegate = FakeProvider(prefix)

    @property
    def calls(self) -> list[tuple[list[str], str]]:
        return self._delegate.calls

    def translate_batch(
        self,
        segments: Sequence[str],
        *,
        system_prompt: str,
    ) -> list[str]:
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise TranslationError("simulated failure")
        return self._delegate.translate_batch(segments, system_prompt=system_prompt)


class FailOnLargeBatchProvider(ITranslationProvider):
    """Fails when batch has more than max_segments segments."""

    def __init__(self, max_segments: int = 1, prefix: str = "翻译:") -> None:
        self.max_segments = max_segments
        self.calls: list[tuple[list[str], str]] = []
        self.prefix = prefix

    def translate_batch(
        self,
        segments: Sequence[str],
        *,
        system_prompt: str,
    ) -> list[str]:
        seg_list = list(segments)
        self.calls.append((seg_list, system_prompt))
        if len(seg_list) > self.max_segments:
            raise TranslationError(f"batch too large: {len(seg_list)} > {self.max_segments}")
        return [f"{self.prefix}{s}" for s in seg_list]


class FakeSource(IBookSource):
    """In-memory book source for testing."""

    def __init__(self, segments: list[Segment] | None = None) -> None:
        self.segments = segments or []
        self.applied: list[TranslatedSegment] | None = None
        self.saved_to: str | None = None

    def get_segments(self) -> list[Segment]:
        return self.segments

    def apply_translations(self, translated: list[TranslatedSegment]) -> None:
        self.applied = translated

    def save(self, output_path: str) -> None:
        self.saved_to = output_path


def _make_segments(texts: list[str]) -> list[Segment]:
    return [Segment(id=f"seg-{i}", text=t) for i, t in enumerate(texts)]


def _default_config(**overrides: object) -> EngineConfig:
    defaults: dict[str, object] = {"system_prompt": "Translate to Chinese."}
    defaults.update(overrides)
    return EngineConfig(**defaults)  # type: ignore[arg-type]


# ── Happy Path ────────────────────────────────────────────────


class TestTranslateHappyPath:
    def test_single_segment(self) -> None:
        provider = FakeProvider()
        source = FakeSource(_make_segments(["Hello"]))
        engine = TranslationEngine(provider, _default_config())

        result = engine.translate(source, "/tmp/out.epub")

        assert result.total_segments == 1
        assert result.total_batches == 1
        assert result.translated_segments == 1
        assert source.saved_to == "/tmp/out.epub"
        assert source.applied is not None
        assert len(source.applied) == 1
        assert source.applied[0].translated == "翻译:Hello"

    def test_multiple_segments_one_batch(self) -> None:
        provider = FakeProvider()
        source = FakeSource(_make_segments(["A", "B", "C"]))
        engine = TranslationEngine(provider, _default_config(max_batch_chars=1000))

        result = engine.translate(source, "/tmp/out.epub")

        assert result.total_segments == 3
        assert result.total_batches == 1
        assert len(provider.calls) == 1
        assert provider.calls[0][0] == ["A", "B", "C"]

    def test_multiple_batches(self) -> None:
        provider = FakeProvider()
        source = FakeSource(_make_segments(["aaa", "bbb", "ccc"]))
        engine = TranslationEngine(
            provider,
            _default_config(max_batch_chars=5, separator_overhead=0),
        )

        result = engine.translate(source, "/tmp/out.epub")

        assert result.total_batches > 1
        assert result.translated_segments == 3
        all_translated = [t.translated for t in source.applied or []]
        assert all_translated == ["翻译:aaa", "翻译:bbb", "翻译:ccc"]

    def test_empty_source(self) -> None:
        provider = FakeProvider()
        source = FakeSource([])
        engine = TranslationEngine(provider, _default_config())

        result = engine.translate(source, "/tmp/out.epub")

        assert result.total_segments == 0
        assert result.total_batches == 0
        assert source.saved_to == "/tmp/out.epub"
        assert len(provider.calls) == 0

    def test_system_prompt_passed_to_provider(self) -> None:
        provider = FakeProvider()
        source = FakeSource(_make_segments(["Hi"]))
        prompt = "You are a professional translator. Target: 中文."
        engine = TranslationEngine(provider, _default_config(system_prompt=prompt))

        engine.translate(source, "/tmp/out.epub")

        assert provider.calls[0][1] == prompt

    def test_segment_ids_preserved(self) -> None:
        segments = [
            Segment(id="ch1/p1", text="One"),
            Segment(id="ch2/p5", text="Two"),
        ]
        provider = FakeProvider()
        source = FakeSource(segments)
        engine = TranslationEngine(provider, _default_config())

        engine.translate(source, "/tmp/out.epub")

        assert source.applied is not None
        ids = [t.id for t in source.applied]
        assert ids == ["ch1/p1", "ch2/p5"]


# ── Callback ──────────────────────────────────────────────────


class TestBatchCallback:
    def test_callback_invoked_per_batch(self) -> None:
        calls: list[tuple[int, int]] = []
        provider = FakeProvider()
        source = FakeSource(_make_segments(["a" * 10, "b" * 10, "c" * 10]))
        engine = TranslationEngine(
            provider,
            _default_config(max_batch_chars=15, separator_overhead=0),
        )

        engine.translate(
            source, "/tmp/out.epub", on_batch_translated=lambda i, t: calls.append((i, t))
        )

        assert len(calls) >= 2
        assert all(total == calls[0][1] for _, total in calls)
        assert [idx for idx, _ in calls] == list(range(len(calls)))


# ── Resilience (split-retry) ─────────────────────────────────


class TestSplitRetryResilience:
    def test_split_on_failure_then_succeed(self) -> None:
        """Provider fails on 2-segment batch but succeeds on singles."""
        provider = FailOnLargeBatchProvider(max_segments=1)
        source = FakeSource(_make_segments(["A", "B"]))
        engine = TranslationEngine(
            provider,
            _default_config(max_batch_chars=1000, max_split_depth=5),
        )

        result = engine.translate(source, "/tmp/out.epub")

        assert result.translated_segments == 2
        assert source.applied is not None
        translations = [t.translated for t in source.applied]
        assert translations == ["翻译:A", "翻译:B"]
        # First call: [A, B] → fail. Then: [A] → ok, [B] → ok = 3 calls
        assert len(provider.calls) == 3

    def test_recursive_split_four_segments(self) -> None:
        """4 segments, provider only handles 1 at a time → 3 levels of splits."""
        provider = FailOnLargeBatchProvider(max_segments=1)
        source = FakeSource(_make_segments(["A", "B", "C", "D"]))
        engine = TranslationEngine(
            provider,
            _default_config(max_batch_chars=10000, max_split_depth=10),
        )

        result = engine.translate(source, "/tmp/out.epub")

        assert result.translated_segments == 4
        translations = [t.translated for t in source.applied or []]
        assert translations == ["翻译:A", "翻译:B", "翻译:C", "翻译:D"]

    def test_max_split_depth_respected(self) -> None:
        """When max_split_depth=0, no splitting is attempted."""
        provider = FailOnLargeBatchProvider(max_segments=1)
        source = FakeSource(_make_segments(["A", "B"]))
        engine = TranslationEngine(
            provider,
            _default_config(max_batch_chars=1000, max_split_depth=0),
        )

        with pytest.raises(TranslationError, match="batch too large"):
            engine.translate(source, "/tmp/out.epub")

    def test_single_segment_failure_propagates(self) -> None:
        """A single segment that fails cannot be split — error propagates."""
        provider = FailThenSucceedProvider(fail_count=999)
        source = FakeSource(_make_segments(["only-one"]))
        engine = TranslationEngine(
            provider,
            _default_config(max_batch_chars=1000, max_split_depth=10),
        )

        with pytest.raises(TranslationError, match="simulated failure"):
            engine.translate(source, "/tmp/out.epub")

    def test_split_preserves_order(self) -> None:
        """After splitting and re-joining, segment order is maintained."""
        provider = FailOnLargeBatchProvider(max_segments=2)
        texts = [f"seg-{i}" for i in range(6)]
        source = FakeSource(_make_segments(texts))
        engine = TranslationEngine(
            provider,
            _default_config(max_batch_chars=10000, max_split_depth=10),
        )

        engine.translate(source, "/tmp/out.epub")

        assert source.applied is not None
        result_originals = [t.original for t in source.applied]
        assert result_originals == texts


# ── Config Validation ─────────────────────────────────────────


class TestEngineConfig:
    def test_frozen(self) -> None:
        cfg = _default_config()
        with pytest.raises(AttributeError):
            cfg.system_prompt = "changed"  # type: ignore[misc]

    def test_defaults(self) -> None:
        cfg = EngineConfig(system_prompt="test")
        assert cfg.max_batch_chars == 60_000
        assert cfg.separator_overhead == 6
        assert cfg.max_split_depth == 10
