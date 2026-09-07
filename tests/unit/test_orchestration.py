"""Application seam contracts independent of argparse and concrete transports."""

import inspect
import ast
import zipfile
from collections.abc import Sequence
from pathlib import Path

import pytest

from ai.orchestration import (
    EpubTranslationOptions,
    TranslationOrchestrator,
    translate_epub,
    translate_markdown,
    translate_pdf,
)
from ai.model_profiles import ResolvedModel
from ai.ports.provider import ITranslationProvider
from ai.ports.provider import ProviderUnavailableError
from ai.orchestration import QualityPolicy


def make_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>',
        )
        archive.writestr(
            "content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata/><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>',
        )
        archive.writestr(
            "chapter.xhtml",
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Example</title></head><body><p>The garden gate was open.</p><p>The moon rose above the hill.</p></body></html>',
        )


def test_epub_application_resumes_without_constructing_provider(tmp_path: Path) -> None:
    class Provider(ITranslationProvider):
        def translate_batch(self, segments: Sequence[str], *, system_prompt: str) -> list[str]:
            return ["花园大门敞开着。", "月亮从山丘上升起。"]

    class Factory:
        calls = 0

        def create(
            self,
            model: ResolvedModel,
            *,
            protocol: str,
            config: dict[str, object],
            allow_paid_api: bool,
            remaining_chars: int,
        ) -> ITranslationProvider:
            self.calls += 1
            assert model.model_id == "gemini-3.8-flash-low"
            return Provider()

    source = tmp_path / "book.epub"
    make_epub(source)
    output = tmp_path / "translated.epub"
    factory = Factory()
    app = TranslationOrchestrator(provider_factory=factory)
    options = EpubTranslationOptions(config={})
    first = app.translate(source, output, options, input_format="epub")
    assert first.translated_segments == 2
    second = app.translate(source, output, options, input_format="epub")
    assert second.resumed_segments == 2
    assert factory.calls == 1
    with zipfile.ZipFile(output) as archive:
        assert "花园大门敞开着。" in archive.read("chapter.xhtml").decode()


def test_public_application_functions_keep_three_arguments() -> None:
    for entrypoint in (translate_epub, translate_markdown, translate_pdf):
        assert list(inspect.signature(entrypoint).parameters) == [
            "input_path",
            "output_path",
            "options",
        ]


def test_cli_does_not_import_concrete_runtime_adapters() -> None:
    import ai.cli

    tree = ast.parse(inspect.getsource(ai.cli))
    forbidden = (
        "ai.adapters",
        "ai.antigravity_provider",
        "ai.runtime_factory",
        "ai.checkpoint_store",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith(forbidden)
        elif isinstance(node, ast.Import):
            assert not any(alias.name.startswith(forbidden) for alias in node.names)


def test_missing_epub_fails_before_runtime_initialization(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        translate_epub(tmp_path / "missing.epub", tmp_path / "out.epub")


def test_interrupted_epub_restores_only_committed_batches(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    class Provider(ITranslationProvider):
        def translate_batch(self, segments: Sequence[str], *, system_prompt: str) -> list[str]:
            calls.append(list(segments))
            if len(calls) == 2:
                raise ProviderUnavailableError("connection interrupted")
            return [
                "花园大门敞开着。" if "garden" in source else "月亮从山丘上升起。"
                for source in segments
            ]

    class Factory:
        def create(
            self,
            model: ResolvedModel,
            *,
            protocol: str,
            config: dict[str, object],
            allow_paid_api: bool,
            remaining_chars: int,
        ) -> ITranslationProvider:
            return Provider()

    source = tmp_path / "book.epub"
    output = tmp_path / "out.epub"
    make_epub(source)
    options = EpubTranslationOptions(config={}, quality=QualityPolicy(max_batch_chars=30))
    app = TranslationOrchestrator(provider_factory=Factory())
    with pytest.raises(ProviderUnavailableError):
        app.translate(source, output, options, input_format="epub")
    assert not output.exists()
    result = app.translate(source, output, options, input_format="epub")
    assert result.resumed_segments == 1
    assert len(calls) == 3
    assert calls[0] == ["The garden gate was open."]
    assert calls[1] == calls[2] == ["The moon rose above the hill."]
