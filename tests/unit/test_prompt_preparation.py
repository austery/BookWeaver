"""Prompt compatibility and local preflight through current application requests."""

from collections.abc import Sequence
from pathlib import Path
from dataclasses import replace
import hashlib
import json

import pytest

from ai.checkpoint_store import CheckpointMismatchError
from ai.model_profiles import ResolvedModel
from ai.orchestration import EpubTranslationOptions, GlossarySpec, TranslationOrchestrator
from ai.ports.provider import ITranslationProvider
from ai.prompt_preparation import PromptPreparation
from tests.unit.test_application_contract import RecordingFactory
from tests.unit.test_orchestration import make_epub


@pytest.mark.parametrize(
    "immersive,expected",
    [
        (False, "4b45b82710fd41716516e028ee98e345e2f76c053df30aa7d29364eb2b90cb57"),
        (True, "07b111c5140ce96409bd3331a77a41bfc25bbf41d166ed79e36c3bb6bbae5e04"),
    ],
)
def test_default_prompt_matches_pre_refactor_bytes(immersive: bool, expected: str) -> None:
    # Golden hashes captured from ee2e8d7's build_system_prompt, not the new renderer.
    prompt = PromptPreparation.from_config(
        {}, output_lang="zh", custom_prompt="Keep numerical ranges exact.", immersive=immersive
    ).render(None)
    assert prompt.sha256 == expected
    assert hashlib.sha256(prompt.text.encode()).hexdigest() == expected


@pytest.mark.parametrize("invalid", ["missing-profile", "missing-file", "legacy-wrapper"])
def test_bad_template_prevents_even_glossary_provider_creation(
    tmp_path: Path, invalid: str
) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    template = tmp_path / "prompt.txt"
    if invalid == "legacy-wrapper":
        template.write_text("<!-- START --> {TARGET_LANGUAGE}")
    config: dict[str, object] = {"prompt_profile": "custom"}
    if invalid != "missing-profile":
        config["prompt_templates"] = {"custom": str(template)}
    factory = RecordingFactory()
    with pytest.raises((ValueError, FileNotFoundError)):
        TranslationOrchestrator(provider_factory=factory).translate(
            source,
            tmp_path / "out.epub",
            EpubTranslationOptions(config=config, glossary=GlossarySpec(extract=True)),
            input_format="epub",
        )
    assert not factory.created
    assert not list(tmp_path.rglob("checkpoint.json"))


def test_template_is_frozen_before_extraction_and_hash_matches_request(tmp_path: Path) -> None:
    source, template = tmp_path / "book.epub", tmp_path / "prompt.txt"
    make_epub(source)
    original = "Translate into {TARGET_LANGUAGE}.\n{GLOSSARY_BLOCK}\n{CUSTOM_INSTRUCTIONS_BLOCK}"
    template.write_text(original)

    class MutatingFactory(RecordingFactory):
        def create(
            self,
            model: ResolvedModel,
            *,
            protocol: str,
            config: dict[str, object],
            allow_paid_api: bool,
            remaining_chars: int,
        ) -> ITranslationProvider:
            delegate = super().create(
                model,
                protocol=protocol,
                config=config,
                allow_paid_api=allow_paid_api,
                remaining_chars=remaining_chars,
            )

            class Provider(ITranslationProvider):
                def translate_batch(
                    self, segments: Sequence[str], *, system_prompt: str
                ) -> list[str]:
                    if protocol == "delimiter":
                        template.write_text("Changed while extraction was running")
                    return delegate.translate_batch(segments, system_prompt=system_prompt)

            return Provider()

    factory = MutatingFactory()
    options = EpubTranslationOptions(
        config={"prompt_profile": "custom", "prompt_templates": {"custom": str(template)}},
        glossary=GlossarySpec(extract=True),
    )
    app = TranslationOrchestrator(provider_factory=factory)
    app.translate(source, tmp_path / "out.epub", options, input_format="epub")
    sent = factory.requests[-1].prompt
    assert sent.startswith("Translate into Chinese.") and "花园" in sent
    data = json.loads(next(tmp_path.rglob("checkpoint.json")).read_text())
    assert data["identity"]["system_prompt_hash"] == hashlib.sha256(sent.encode()).hexdigest()
    # The v1 cache-key recipe is an independent compatibility oracle.
    signature = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    cache_identity = json.dumps(
        {
            "source": signature,
            "mode": "auto",
            "max_terms": 20,
            "model": "gemini-3.1-pro-low",
            "effort": "low",
            "extractor_version": 1,
        },
        sort_keys=True,
    )
    cache = (
        tmp_path
        / ".bookweaver_glossaries"
        / (hashlib.sha256(cache_identity.encode()).hexdigest() + ".json")
    )
    assert cache.exists()
    before = len(factory.created)
    with pytest.raises(CheckpointMismatchError):
        app.translate(source, tmp_path / "out.epub", options, input_format="epub")
    assert len(factory.created) == before
    template.write_text(original)
    result = app.translate(source, tmp_path / "out.epub", replace(options), input_format="epub")
    assert result.resumed_segments == 2 and len(factory.created) == before
