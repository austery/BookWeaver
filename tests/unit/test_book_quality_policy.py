"""Observed book-quality failures and supported policy boundaries."""

from dataclasses import replace
from pathlib import Path

import pytest

from ai.core.batcher import TextBatcher
from ai.epub_package import extract_translatable_segments, patch_xhtml_alternating
from ai.checkpoint_store import CheckpointStore, CheckpointMismatchError
from tests.unit.test_checkpoint_store import identity


@pytest.mark.parametrize("heading", ["Works Cited", "Bibliography", "References"])
def test_dedicated_bibliography_is_source_only(heading: str) -> None:
    source = (
        f"<html><body><h2><a>{heading}</a></h2><p>Author. Book. Publisher, 2009.</p></body></html>"
    )
    assert extract_translatable_segments(source) == []
    assert patch_xhtml_alternating(source, []) == source
    with pytest.raises(ValueError):
        patch_xhtml_alternating(source, ["Duplicate citation"])


def test_bibliography_semantics_and_prose_boundary() -> None:
    source = '<html xmlns:epub="http://www.idpf.org/2007/ops"><body epub:type="bibliography"><p>Author. Book. 2009.</p></body></html>'
    assert extract_translatable_segments(source) == []
    prose = "<html><body><h2>How to Read References</h2><p>The bibliography is useful.</p><h2>References</h2><p>A cited book.</p></body></html>"
    assert extract_translatable_segments(prose)
    leading_prose = "<html><body><p>Chapter discussion.</p><h2>References</h2><p>A cited book.</p></body></html>"
    assert extract_translatable_segments(leading_prose)


def test_batch_limits_preserve_every_segment_and_order() -> None:
    texts = [str(i) for i in range(919)]
    batches = TextBatcher(60000, 6, max_batch_segments=200).plan_batches(texts)
    assert [len(b) for b in batches] == [200, 200, 200, 200, 119]
    assert [s for b in batches for s in b] == texts
    assert TextBatcher(5, 1, max_batch_segments=2).plan_batches(["aaa", "bb", "c", "d"]) == [
        ["aaa"],
        ["bb", "c"],
        ["d"],
    ]


@pytest.mark.parametrize("limit", [0, -1])
def test_invalid_segment_limit_is_rejected(limit: int) -> None:
    with pytest.raises(ValueError):
        TextBatcher(60000, max_batch_segments=limit)


def test_segment_cap_is_soft_checkpoint_compatibility(tmp_path: Path) -> None:
    with CheckpointStore(tmp_path) as store:
        store.save(identity(), {})
        selected = replace(identity(), max_batch_segments=200)
        with pytest.raises(CheckpointMismatchError, match="max_batch_segments"):
            store.load(selected, segment_ids=set())
        assert store.load(selected, segment_ids=set(), force=True) == {}


def test_mixed_document_is_not_treated_as_entire_bibliography() -> None:
    mixed = "<html><body><h2>References</h2><p>A book.</p><h2>Afterword</h2><p>New prose.</p></body></html>"
    assert extract_translatable_segments(mixed)


def test_public_application_honors_segment_cap_from_config(tmp_path: Path) -> None:
    from ai.orchestration import TranslationOrchestrator, EpubTranslationOptions, QualityPolicy
    from tests.unit.test_orchestration import make_epub
    from tests.unit.test_review_regressions import OfflineFactory

    source = tmp_path / "book.epub"
    make_epub(source)
    factory = OfflineFactory()
    result = TranslationOrchestrator(provider_factory=factory).translate(
        source,
        tmp_path / "out.epub",
        EpubTranslationOptions(config={"epub_resilience": {"max_batch_segments": 1}}),
        input_format="epub",
    )
    assert result.total_batches == 2
    assert factory.calls == ["segment_tags", "segment_tags"]
    # Explicit options take precedence over config in a fresh run.
    result = TranslationOrchestrator(provider_factory=OfflineFactory()).translate(
        source,
        tmp_path / "other" / "out.epub",
        EpubTranslationOptions(
            config={"epub_resilience": {"max_batch_segments": 1}},
            quality=QualityPolicy(max_batch_segments=2),
        ),
        input_format="epub",
    )
    assert result.total_batches == 1


def test_cli_forwards_segment_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import ai.cli
    from ai.orchestration import EpubTranslationOptions
    from tests.unit.test_orchestration import make_epub

    source = tmp_path / "book.epub"
    make_epub(source)
    captured: list[int | None] = []

    def translate(input_path: Path, output_path: Path, options: EpubTranslationOptions) -> None:
        captured.append(options.quality.max_batch_segments)

    monkeypatch.setattr(ai.cli.orchestration, "translate_epub", translate)
    ai.cli.main(
        [str(source), "--output", str(tmp_path / "out.epub"), "--max-batch-segments", "150"]
    )
    assert captured == [150]


def test_old_identity_without_cap_means_unbounded(tmp_path: Path) -> None:
    import json

    with CheckpointStore(tmp_path) as store:
        store.save(identity(), {})
        path = tmp_path / "checkpoint.json"
        data = json.loads(path.read_text())
        del data["identity"]["max_batch_segments"]
        path.write_text(json.dumps(data))
        assert store.load(identity(), segment_ids=set()) == {}
        with pytest.raises(CheckpointMismatchError, match="max_batch_segments"):
            store.load(replace(identity(), max_batch_segments=200), segment_ids=set())


def test_epub_adapter_leaves_bibliography_bytes_untouched(tmp_path: Path) -> None:
    import zipfile

    from ai.adapters.sources.epub_adapter import EpubSourceAdapter
    from ai.ports.source import TranslatedSegment
    from tests.unit.test_orchestration import make_epub

    source = tmp_path / "book.epub"
    make_epub(source)
    with zipfile.ZipFile(source) as archive:
        entries = [(info, archive.read(info.filename)) for info in archive.infolist()]
    candidates = [info.filename for info, _ in entries if info.filename.endswith(".xhtml")]
    bibliography_path = candidates[-1]
    bibliography = b'<html xmlns="http://www.w3.org/1999/xhtml"><body><h2>References</h2><p>Author. Title. 2009.</p></body></html>'
    with zipfile.ZipFile(source, "w") as archive:
        for info, data in entries:
            archive.writestr(info, bibliography if info.filename == bibliography_path else data)
    adapter = EpubSourceAdapter(source)
    segments = adapter.get_segments()
    assert not any(s.id.startswith(bibliography_path + "::") for s in segments)
    adapter.apply_translations([TranslatedSegment(s.id, s.text, "译文") for s in segments])
    output = tmp_path / "out.epub"
    adapter.save(str(output))
    with zipfile.ZipFile(output) as archive:
        assert archive.read(bibliography_path) == bibliography


@pytest.mark.parametrize(
    "marker",
    ["", '<a id="intro"/>', '<span role="doc-pagebreak"/>', '<span><a id="nested"/></span>'],
)
def test_leading_prose_in_tails_remains_translatable(marker: str, tmp_path: Path) -> None:
    import zipfile
    from ai.orchestration import TranslationOrchestrator, EpubTranslationOptions
    from tests.unit.test_orchestration import make_epub
    from tests.unit.test_review_regressions import OfflineFactory

    xhtml = f'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>{marker}This is substantive chapter prose.</p><h2>References</h2><p>A cited book.</p></body></html>'
    assert len(extract_translatable_segments(xhtml)) == 2
    patched = patch_xhtml_alternating(xhtml, ["这是正文。", "引用书籍。"])
    assert "这是正文。" in patched
    source = tmp_path / "book.epub"
    make_epub(source)
    with zipfile.ZipFile(source) as archive:
        entries = [(info, archive.read(info.filename)) for info in archive.infolist()]
    with zipfile.ZipFile(source, "w") as archive:
        for info, data in entries:
            archive.writestr(info, xhtml.encode() if info.filename == "chapter.xhtml" else data)
    factory = OfflineFactory()
    output = tmp_path / "out.epub"
    result = TranslationOrchestrator(provider_factory=factory).translate(
        source, output, EpubTranslationOptions(config={}), input_format="epub"
    )
    assert result.total_segments == 2
    assert factory.calls == ["segment_tags"]
    with zipfile.ZipFile(output) as archive:
        assert archive.read("chapter.xhtml").count(b'class="bw-translation"') == 2
