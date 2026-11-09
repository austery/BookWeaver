"""Current application behavior using real EPUB packages and an offline provider."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import json

import pytest

from tests.runtime_fakes import NoAuditFactory

from ai.model_profiles import ResolvedModel
from ai.orchestration import (
    ProviderSpec,
    EpubTranslationOptions,
    GlossarySpec,
    ModelSpec,
    QualityPolicy,
    TranslationOrchestrator,
)
from ai.ports.provider import ITranslationProvider
from tests.unit.test_orchestration import make_epub, make_indexed_epub


@dataclass(frozen=True)
class Request:
    model: ResolvedModel
    protocol: str
    segments: tuple[str, ...]
    prompt: str


class RecordingFactory(NoAuditFactory):
    def __init__(self, *, translation: str = "花园大门敞开着。") -> None:
        self.requests: list[Request] = []
        self.created: list[ResolvedModel] = []
        self.translation = translation

    def create(
        self,
        model: ResolvedModel,
        *,
        protocol: str,
        config: dict[str, object],
        allow_paid_api: bool,
        remaining_chars: int,
    ) -> ITranslationProvider:
        self.created.append(model)
        factory = self

        class Provider(ITranslationProvider):
            def translate_batch(self, segments: Sequence[str], *, system_prompt: str) -> list[str]:
                factory.requests.append(Request(model, protocol, tuple(segments), system_prompt))
                if protocol == "delimiter":
                    return [
                        '{"critical_terminology": [{"term": "garden", "suggested_translation": "花园", "priority": "high"}]}'
                    ]
                return [factory.translation for _ in segments]

        return Provider()


@pytest.mark.parametrize("profile", ["flash", "pro"])
@pytest.mark.parametrize("limit_source", ["default", "config", "override"])
def test_application_resolves_profile_and_batch_precedence(
    tmp_path: Path, profile: str, limit_source: str
) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    factory = RecordingFactory()
    config: dict[str, object] = {}
    if limit_source != "default":
        key = "pro_epub_max_batch_chars" if profile == "pro" else "standard_epub_max_batch_chars"
        config = {"epub_resilience": {key: 30}}
    options = EpubTranslationOptions(
        config=config,
        model=ModelSpec(requested=profile),
        quality=QualityPolicy(max_batch_chars=60000 if limit_source == "override" else None),
    )
    result = TranslationOrchestrator(provider_factory=factory).translate(
        source, tmp_path / "out.epub", options, input_format="epub"
    )
    assert result.total_batches == (2 if limit_source == "config" else 1)
    assert {request.model.profile for request in factory.requests} == {profile}
    assert all(request.model.effort == "low" for request in factory.requests)
    assert sum(len(request.segments) for request in factory.requests) == 2


def test_automatic_terms_stop_a_book_without_an_index_before_any_model_call(
    tmp_path: Path,
) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    factory = RecordingFactory()
    with pytest.raises(ValueError, match="--glossary-mode deep-scan"):
        TranslationOrchestrator(provider_factory=factory).translate(
            source,
            tmp_path / "out.epub",
            EpubTranslationOptions(config={}, glossary=GlossarySpec(mode="auto", extract=True)),
            input_format="epub",
        )
    assert factory.requests == []
    assert not (tmp_path / "out.epub").exists()


@pytest.mark.parametrize("mode", ["auto", "deep-scan", "manual"])
def test_glossary_selection_and_injection_through_application(tmp_path: Path, mode: str) -> None:
    source = tmp_path / "book.epub"
    make_indexed_epub(source)
    manual = tmp_path / "manual.json"
    manual.write_text(
        '{"critical_terminology": [{"term": "garden", "suggested_translation": "花园", "priority": "high"}]}'
    )
    factory = RecordingFactory()
    result = TranslationOrchestrator(provider_factory=factory).translate(
        source,
        tmp_path / "out.epub",
        EpubTranslationOptions(
            config={},
            glossary=GlossarySpec(
                path=manual if mode == "manual" else None,
                mode="deep-scan" if mode == "manual" else mode,
                extract=True,
                max_terms=1,
            ),
        ),
        input_format="epub",
    )
    assert [request.protocol for request in factory.requests] == (
        ["segment_tags"] if mode == "manual" else ["delimiter", "segment_tags"]
    )
    assert factory.requests[-1].model.profile == "flash"
    assert "garden" in factory.requests[-1].prompt and "花园" in factory.requests[-1].prompt
    assert result.glossary_used is not None
    if mode != "manual":
        assert factory.requests[0].model.profile == "pro"


@pytest.mark.parametrize("disabled_by", [None, "options", "config"])
def test_sanity_probe_observes_without_blocking_checkpoint_persistence(
    tmp_path: Path, disabled_by: str | None
) -> None:
    source, output = tmp_path / "book.epub", tmp_path / "out.epub"
    make_epub(source)
    factory = RecordingFactory(translation="x")
    options = EpubTranslationOptions(
        config={"sanity_probe": {"enabled": False}} if disabled_by == "config" else {},
        quality=QualityPolicy(sanity_probe=disabled_by != "options"),
    )
    TranslationOrchestrator(provider_factory=factory).translate(
        source, output, options, input_format="epub"
    )
    checkpoint = json.loads(next(tmp_path.rglob("checkpoint.json")).read_text())
    assert len(checkpoint["segments"]) == 2
    assert output.exists()
    warnings = list(tmp_path.rglob("warnings.json"))
    if disabled_by is None:
        entries = json.loads(warnings[0].read_text())["warnings"]
        assert {entry["check"] for entry in entries} == {"length_ratio"}
        assert {entry["segment_id"] for entry in entries} == set(checkpoint["segments"])
    else:
        assert warnings == []


@pytest.mark.parametrize("invalid", ["model", "batch", "glossary", "source-output"])
def test_invalid_application_intent_never_constructs_provider(tmp_path: Path, invalid: str) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    original = source.read_bytes()
    factory = RecordingFactory()
    options = EpubTranslationOptions(
        config={},
        model=ModelSpec(requested="missing" if invalid == "model" else "flash"),
        quality=QualityPolicy(max_batch_chars=0 if invalid == "batch" else None),
        glossary=GlossarySpec(max_terms=0 if invalid == "glossary" else None),
    )
    with pytest.raises(ValueError):
        TranslationOrchestrator(provider_factory=factory).translate(
            source,
            source if invalid == "source-output" else tmp_path / "out.epub",
            options,
            input_format="epub",
        )
    assert not factory.created
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "provider,effort",
    [("openai", None), ("api", None), ("anthropic", "low"), ("cli", None)],
)
def test_unavailable_metered_selection_never_constructs_provider(
    tmp_path: Path, provider: str, effort: str | None
) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    factory = RecordingFactory()
    options = EpubTranslationOptions(
        config={},
        model=ModelSpec(effort=effort),
        provider=ProviderSpec(name=provider, allow_paid_api=provider == "cli"),
    )
    with pytest.raises(ValueError):
        TranslationOrchestrator(provider_factory=factory).translate(
            source, tmp_path / "out.epub", options, input_format="epub"
        )
    assert not factory.created


def test_a_saved_glossary_keeps_its_prompt_and_the_run_reports_term_usage(tmp_path: Path) -> None:
    """A glossary on disk stays byte-stable for resume, even with two options for one term."""
    source = tmp_path / "book.epub"
    make_indexed_epub(source)
    manual = tmp_path / "manual.json"
    manual.write_text(
        '{"critical_terminology": [{"term": "garden", "suggested_translation": "花园 / 园子", '
        '"priority": "high"}]}',
        encoding="utf-8",
    )
    factory = RecordingFactory()
    factory.translation = "园子"
    output = tmp_path / "out.epub"

    TranslationOrchestrator(provider_factory=factory).translate(
        source,
        output,
        EpubTranslationOptions(config={}, glossary=GlossarySpec(path=manual)),
        input_format="epub",
    )

    assert "花园 / 园子" in factory.requests[-1].prompt
    reports = list(tmp_path.rglob("term-consistency.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["terms"][0]["term"] == "garden"
    assert report["terms"][0]["segments"] > 0
    assert report["terms"][0]["option_counts"] == {
        "花园": 0,
        "园子": report["terms"][0]["segments"],
    }
