"""Current application behavior using real EPUB packages and an offline provider."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import json

import pytest

from ai.model_profiles import ResolvedModel
from ai.orchestration import (
    EpubTranslationOptions,
    GlossarySpec,
    ModelSpec,
    QualityPolicy,
    TranslationOrchestrator,
)
from ai.ports.provider import ITranslationProvider, TranslationError
from tests.unit.test_orchestration import make_epub


@dataclass(frozen=True)
class Request:
    model: ResolvedModel
    protocol: str
    segments: tuple[str, ...]
    prompt: str


class RecordingFactory:
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


@pytest.mark.parametrize("mode", ["auto", "deep-scan", "manual"])
def test_glossary_selection_and_injection_through_application(tmp_path: Path, mode: str) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
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
def test_sanity_validation_precedes_checkpoint_persistence(
    tmp_path: Path, disabled_by: str | None
) -> None:
    source, output = tmp_path / "book.epub", tmp_path / "out.epub"
    make_epub(source)
    factory = RecordingFactory(translation="x")
    options = EpubTranslationOptions(
        config={"sanity_probe": {"enabled": False}} if disabled_by == "config" else {},
        quality=QualityPolicy(sanity_probe=disabled_by != "options"),
    )
    app = TranslationOrchestrator(provider_factory=factory)
    if disabled_by is None:
        with pytest.raises(TranslationError, match="sanity check"):
            app.translate(source, output, options, input_format="epub")
        assert not list(tmp_path.rglob("checkpoint.json"))
        assert not output.exists()
    else:
        app.translate(source, output, options, input_format="epub")
        checkpoint = json.loads(next(tmp_path.rglob("checkpoint.json")).read_text())
        assert len(checkpoint["segments"]) == 2
        assert output.exists()


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
