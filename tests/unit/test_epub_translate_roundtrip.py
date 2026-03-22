from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import pytest


def _load_roundtrip_cli_module():
    project_root = Path(__file__).resolve().parents[2]
    file_path = project_root / "09_epub_translate_roundtrip.py"
    spec = importlib.util.spec_from_file_location("step9_module", file_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load 09_epub_translate_roundtrip.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _translate_with_batch_separator(text: str) -> str:
    if "%%" in text:
        parts = [part.strip() for part in text.split("\n\n%%\n\n")]
        return "\n\n%%\n\n".join(f"ZH:{part}" for part in parts)
    return f"ZH:{text}"


def _build_min_epub(
    path: Path,
    *,
    broken_fragment: bool = False,
    missing_cover_asset: bool = False,
    paragraphs: list[str] | None = None,
) -> None:
    fragment = "missing" if broken_fragment else "anchor"
    body_paragraphs = paragraphs or ["Hello."]
    body_html = "".join(f"<p>{text}</p>" for text in body_paragraphs)
    with zipfile.ZipFile(path, "w") as zip_file:
        zip_file.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zip_file.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""",
        )
        zip_file.writestr(
            "content.opf",
            """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Demo</dc:title><dc:language>en</dc:language><dc:identifier id="uid">id</dc:identifier>
    <meta name="cover" content="cover-image"/>
  </metadata>
  <manifest>
    <item id="cover-image" href="cover.jpg" media-type="image/jpeg"/>
    <item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="toc"><itemref idref="c1"/></spine>
</package>""",
        )
        zip_file.writestr(
            "chapter1.xhtml",
            (
                "<html xmlns='http://www.w3.org/1999/xhtml'>"
                f"<body><a href='chapter1.xhtml#{fragment}'>go</a>"
                "<p id='anchor'>Anchor</p>"
                f"{body_html}</body></html>"
            ),
        )
        zip_file.writestr("toc.ncx", "<ncx><navMap></navMap></ncx>")
        if not missing_cover_asset:
            zip_file.writestr("cover.jpg", "x")


def _build_two_chapter_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zip_file:
        zip_file.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zip_file.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""",
        )
        zip_file.writestr(
            "content.opf",
            """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Demo</dc:title><dc:language>en</dc:language><dc:identifier id="uid">id</dc:identifier>
    <meta name="cover" content="cover-image"/>
  </metadata>
  <manifest>
    <item id="cover-image" href="cover.jpg" media-type="image/jpeg"/>
    <item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="toc"><itemref idref="c1"/><itemref idref="c2"/></spine>
</package>""",
        )
        zip_file.writestr(
            "chapter1.xhtml",
            ("<html xmlns='http://www.w3.org/1999/xhtml'><body><p>Doc1</p></body></html>"),
        )
        zip_file.writestr(
            "chapter2.xhtml",
            ("<html xmlns='http://www.w3.org/1999/xhtml'><body><p>Doc2</p></body></html>"),
        )
        zip_file.writestr("toc.ncx", "<ncx><navMap></navMap></ncx>")
        zip_file.writestr("cover.jpg", "x")


def test_plan_segment_batches_enforces_limits_and_order() -> None:
    from ai.epub_translate_roundtrip import plan_segment_batches

    segments = [f"S{i}-" + ("x" * 500) for i in range(130)]
    batches = plan_segment_batches(
        segments,
        max_batch_chars=18_000,
        max_batch_segments=36,
    )

    assert [len(batch) for batch in batches] == [35, 35, 35, 25]
    assert all(1 <= len(batch) <= 36 for batch in batches)
    assert [item for batch in batches for item in batch] == segments


def test_plan_segment_batches_allows_single_oversized_segment() -> None:
    from ai.epub_translate_roundtrip import plan_segment_batches

    oversized = "y" * 30_000
    batches = plan_segment_batches(
        [oversized, "ok"],
        max_batch_chars=18_000,
        max_batch_segments=36,
    )

    assert len(batches) == 2
    assert batches[0] == [oversized]
    assert batches[1] == ["ok"]


def test_select_context_docs_prefers_toc_preface_ch1() -> None:
    from ai.epub_package import EpubPackageModel, ManifestItem
    from ai.epub_translate_roundtrip import _select_context_docs

    model = EpubPackageModel(
        epub_path=Path("book.epub"),
        opf_path="OEBPS/content.opf",
        cover_item_id=None,
        spine_itemrefs=["preface", "chapter-1", "chapter-2"],
        manifest_items={
            "nav": ManifestItem(
                id="nav",
                href="nav.xhtml",
                media_type="application/xhtml+xml",
            ),
            "preface": ManifestItem(
                id="preface",
                href="preface.xhtml",
                media_type="application/xhtml+xml",
            ),
            "chapter-1": ManifestItem(
                id="chapter-1",
                href="chapter1.xhtml",
                media_type="application/xhtml+xml",
            ),
            "chapter-2": ManifestItem(
                id="chapter-2",
                href="chapter2.xhtml",
                media_type="application/xhtml+xml",
            ),
            "toc-ncx": ManifestItem(
                id="toc-ncx",
                href="toc.ncx",
                media_type="application/x-dtbncx+xml",
            ),
        },
        toc_item_id="toc-ncx",
    )

    assert _select_context_docs(model) == [
        "OEBPS/nav.xhtml",
        "OEBPS/preface.xhtml",
        "OEBPS/chapter1.xhtml",
    ]


def test_select_context_docs_handles_missing_preface() -> None:
    from ai.epub_package import EpubPackageModel, ManifestItem
    from ai.epub_translate_roundtrip import _select_context_docs

    model = EpubPackageModel(
        epub_path=Path("book.epub"),
        opf_path="OEBPS/content.opf",
        cover_item_id=None,
        spine_itemrefs=["chapter-1", "chapter-2"],
        manifest_items={
            "nav": ManifestItem(
                id="nav",
                href="nav.xhtml",
                media_type="application/xhtml+xml",
            ),
            "chapter-1": ManifestItem(
                id="chapter-1",
                href="chapter1.xhtml",
                media_type="application/xhtml+xml",
            ),
            "chapter-2": ManifestItem(
                id="chapter-2",
                href="chapter2.xhtml",
                media_type="application/xhtml+xml",
            ),
        },
        toc_item_id=None,
    )

    assert _select_context_docs(model) == [
        "OEBPS/nav.xhtml",
        "OEBPS/chapter1.xhtml",
    ]


def test_select_context_docs_avoids_chapter10_false_match() -> None:
    from ai.epub_package import EpubPackageModel, ManifestItem
    from ai.epub_translate_roundtrip import _select_context_docs

    model = EpubPackageModel(
        epub_path=Path("book.epub"),
        opf_path="OEBPS/content.opf",
        cover_item_id=None,
        spine_itemrefs=["chapter-10", "chapter-1"],
        manifest_items={
            "chapter-10": ManifestItem(
                id="chapter-10",
                href="chapter10.xhtml",
                media_type="application/xhtml+xml",
            ),
            "chapter-1": ManifestItem(
                id="chapter-1",
                href="chapter1.xhtml",
                media_type="application/xhtml+xml",
            ),
        },
        toc_item_id=None,
    )

    assert _select_context_docs(model) == ["OEBPS/chapter1.xhtml"]


def test_select_context_docs_preface_match_is_case_insensitive() -> None:
    from ai.epub_package import EpubPackageModel, ManifestItem
    from ai.epub_translate_roundtrip import _select_context_docs

    model = EpubPackageModel(
        epub_path=Path("book.epub"),
        opf_path="OEBPS/content.opf",
        cover_item_id=None,
        spine_itemrefs=["preface", "ch1"],
        manifest_items={
            "preface": ManifestItem(
                id="PREFACE",
                href="Preface.XHTML",
                media_type="application/xhtml+xml",
            ),
            "ch1": ManifestItem(
                id="CH01",
                href="CH01.xhtml",
                media_type="application/xhtml+xml",
            ),
        },
        toc_item_id=None,
    )

    assert _select_context_docs(model) == [
        "OEBPS/Preface.XHTML",
        "OEBPS/CH01.xhtml",
    ]


def test_select_context_docs_skips_non_xhtml_items() -> None:
    from ai.epub_package import EpubPackageModel, ManifestItem
    from ai.epub_translate_roundtrip import _select_context_docs

    model = EpubPackageModel(
        epub_path=Path("book.epub"),
        opf_path="OEBPS/content.opf",
        cover_item_id=None,
        spine_itemrefs=["chapter-1", "chapter-2"],
        manifest_items={
            "chapter-1": ManifestItem(
                id="chapter-1",
                href="chapter1.html",
                media_type="text/html",
            ),
            "chapter-2": ManifestItem(
                id="chapter-2",
                href="chapter2.xhtml",
                media_type="application/xhtml+xml",
            ),
        },
        toc_item_id=None,
    )

    assert _select_context_docs(model) == []


def test_context_sampling_enforces_per_doc_and_global_limits() -> None:
    from ai.epub_translate_roundtrip import _sample_context_paragraphs

    def _xhtml(doc_label: str, count: int) -> str:
        paragraphs = "".join(f"<p>{doc_label}-{index}</p>" for index in range(1, count + 1))
        return f"<html xmlns='http://www.w3.org/1999/xhtml'><body>{paragraphs}</body></html>"

    selected_doc_paths = [
        "OEBPS/preface.xhtml",
        "OEBPS/chapter1.xhtml",
        "OEBPS/chapter2.xhtml",
    ]
    source_docs = {
        "OEBPS/preface.xhtml": _xhtml("preface", 10),
        "OEBPS/chapter1.xhtml": _xhtml("chapter1", 10),
        "OEBPS/chapter2.xhtml": _xhtml("chapter2", 10),
    }

    sampled = _sample_context_paragraphs(
        selected_doc_paths=selected_doc_paths,
        source_docs=source_docs,
        max_paragraphs_per_doc=3,
        max_paragraphs_total=7,
    )

    assert len(sampled) == 7
    assert [item.doc_path for item in sampled] == [
        "OEBPS/preface.xhtml",
        "OEBPS/preface.xhtml",
        "OEBPS/preface.xhtml",
        "OEBPS/chapter1.xhtml",
        "OEBPS/chapter1.xhtml",
        "OEBPS/chapter1.xhtml",
        "OEBPS/chapter2.xhtml",
    ]
    assert [item.text for item in sampled] == [
        "preface-1",
        "preface-2",
        "preface-3",
        "chapter1-1",
        "chapter1-2",
        "chapter1-3",
        "chapter2-1",
    ]
    assert (
        max(
            len([item for item in sampled if item.doc_path == doc_path])
            for doc_path in selected_doc_paths
        )
        <= 3
    )


def test_context_pass_writes_analysis_prompt_and_manifest() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book.epub"
        output_epub = Path(temp_dir) / "translated.epub"
        _build_min_epub(source_epub, paragraphs=["Alpha", "Beta", "Gamma"])

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt="Use concise tone.",
            translate_fn=_translate_with_batch_separator,
        )

        artifacts_dir = output_epub.parent / "epub_orchestration"
        analysis_path = artifacts_dir / "01-analysis.md"
        prompt_path = artifacts_dir / "02-prompt.md"
        manifest_path = artifacts_dir / "context_manifest.json"

        assert analysis_path.exists()
        assert prompt_path.exists()
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert isinstance(manifest.get("selected_docs"), list)
        assert isinstance(manifest.get("sampled_total"), int)
        assert isinstance(manifest.get("context_signature"), str)
        assert isinstance(manifest.get("prompt_hash"), str)


def test_roundtrip_uses_context_prompt_instead_of_inline_immersive_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai.epub_context_pass import EpubContextArtifacts
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book.epub"
        output_epub = Path(temp_dir) / "translated.epub"
        _build_min_epub(source_epub, paragraphs=["Alpha", "Beta"])

        context_prompt = "CONTEXT_PROMPT_MARKER"
        captured_prompts: list[str] = []

        def fake_context_pass(**_: object) -> EpubContextArtifacts:
            artifacts_dir = output_epub.parent / "epub_orchestration"
            return EpubContextArtifacts(
                analysis_path=artifacts_dir / "01-analysis.md",
                prompt_path=artifacts_dir / "02-prompt.md",
                manifest_path=artifacts_dir / "context_manifest.json",
                context_signature="ctx-signature",
                prompt_hash="ctx-prompt-hash",
                prompt_text=context_prompt,
            )

        def fake_translate_chunk(
            self: object,
            text: str,
            chunk_size: int,
            system_prompt: str,
            timeout_seconds: int = 180,
        ) -> str:
            del self, chunk_size, timeout_seconds
            captured_prompts.append(system_prompt)
            return _translate_with_batch_separator(text)

        monkeypatch.setattr("ai.epub_translate_roundtrip.run_epub_context_pass", fake_context_pass)
        monkeypatch.setattr(
            "ai.gemini_provider.GeminiProvider.translate_chunk", fake_translate_chunk
        )

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=None,
        )

        assert captured_prompts
        assert all(prompt == context_prompt for prompt in captured_prompts)


def test_translate_roundtrip_rewrites_spine_xhtml_and_preserves_toc_file() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book.epub"
        output_epub = Path(temp_dir) / "translated.epub"
        _build_min_epub(source_epub)

        with zipfile.ZipFile(source_epub, "r") as source_zip:
            toc_before = source_zip.read("toc.ncx")

        result = run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=_translate_with_batch_separator,
        )

        assert result.output_epub.exists()
        assert result.translated_segments > 0

        with zipfile.ZipFile(output_epub, "r") as output_zip:
            toc_after = output_zip.read("toc.ncx")
            chapter = output_zip.read("chapter1.xhtml").decode("utf-8")

        assert toc_before == toc_after
        assert "Hello." in chapter
        assert "ZH:Hello." in chapter


def test_translate_roundtrip_allows_preexisting_broken_fragment_links() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-broken.epub"
        output_epub = Path(temp_dir) / "translated-broken.epub"
        _build_min_epub(source_epub, broken_fragment=True)

        result = run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=lambda text: f"ZH:{text}",
        )
        assert result.output_epub.exists()


def test_translate_roundtrip_fails_on_missing_manifest_asset() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-missing-asset.epub"
        output_epub = Path(temp_dir) / "translated-missing-asset.epub"
        _build_min_epub(source_epub, missing_cover_asset=True)

        with pytest.raises(RuntimeError, match="missing manifest asset"):
            run_translate_roundtrip(
                source_epub=source_epub,
                output_epub=output_epub,
                output_lang="zh",
                bilingual_style="alternating",
                model="gemini-2.5-flash",
                custom_prompt=None,
                translate_fn=lambda text: f"ZH:{text}",
            )


def test_translate_roundtrip_uses_batch_call_per_doc() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-batch.epub"
        output_epub = Path(temp_dir) / "translated-batch.epub"
        _build_min_epub(source_epub, paragraphs=["P1", "P2", "P3"])

        call_count = 0

        def batch_translate(text: str) -> str:
            nonlocal call_count
            call_count += 1
            return _translate_with_batch_separator(text)

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=batch_translate,
        )

        assert call_count == 1


def test_translate_roundtrip_retries_with_split_on_batch_mismatch() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-retry.epub"
        output_epub = Path(temp_dir) / "translated-retry.epub"
        _build_min_epub(source_epub, paragraphs=["A", "B", "C", "D"])

        calls: list[str] = []
        mismatch_injected = False

        def flaky_batch_translate(text: str) -> str:
            nonlocal mismatch_injected
            calls.append(text)
            if "%%" not in text:
                return _translate_with_batch_separator(text)
            if not mismatch_injected:
                mismatch_injected = True
                return "BROKEN"
            return _translate_with_batch_separator(text)

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=flaky_batch_translate,
        )

        assert any("%%" in payload for payload in calls)
        assert len(calls) > 1


def test_translate_roundtrip_retries_with_split_on_batch_timeout() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-timeout.epub"
        output_epub = Path(temp_dir) / "translated-timeout.epub"
        _build_min_epub(source_epub, paragraphs=["A", "B", "C", "D"])

        calls: list[str] = []
        timeout_injected = False

        def timeout_then_translate(text: str) -> str:
            nonlocal timeout_injected
            calls.append(text)
            if "%%" in text and not timeout_injected:
                timeout_injected = True
                raise subprocess.TimeoutExpired(
                    cmd=["gemini", "--model", "gemini-3-pro-preview"], timeout=180
                )
            return _translate_with_batch_separator(text)

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=timeout_then_translate,
        )

        assert timeout_injected
        assert len(calls) > 1


def test_translate_roundtrip_prebatches_pro_requests_before_retry() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-pro-prebatch.epub"
        output_epub = Path(temp_dir) / "translated-pro-prebatch.epub"
        paragraphs = [f"P{i}-" + ("x" * 500) for i in range(80)]
        _build_min_epub(source_epub, paragraphs=paragraphs)

        calls: list[str] = []

        def batch_translate(text: str) -> str:
            calls.append(text)
            return _translate_with_batch_separator(text)

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="pro",
            custom_prompt=None,
            translate_fn=batch_translate,
        )

        assert len(calls) > 1
        assert max(len(payload.split("\n\n%%\n\n")) for payload in calls) <= 36


def test_translate_roundtrip_flash_keeps_single_doc_batch() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-flash-single-batch.epub"
        output_epub = Path(temp_dir) / "translated-flash-single-batch.epub"
        paragraphs = [f"P{i}-" + ("x" * 500) for i in range(80)]
        _build_min_epub(source_epub, paragraphs=paragraphs)

        call_count = 0

        def batch_translate(text: str) -> str:
            nonlocal call_count
            call_count += 1
            return _translate_with_batch_separator(text)

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="flash",
            custom_prompt=None,
            translate_fn=batch_translate,
        )

        assert call_count == 1


def test_translate_roundtrip_logs_planned_batch_summary_for_pro(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-log-prebatch.epub"
        output_epub = Path(temp_dir) / "translated-log-prebatch.epub"
        paragraphs = [f"P{i}-" + ("x" * 500) for i in range(80)]
        _build_min_epub(source_epub, paragraphs=paragraphs)

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="pro",
            custom_prompt=None,
            translate_fn=_translate_with_batch_separator,
        )

        stdout = capsys.readouterr().out
        assert "planned_batches=" in stdout
        assert "batch 1/" in stdout


def test_translate_roundtrip_resume_skips_completed_docs() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-resume.epub"
        output_epub = Path(temp_dir) / "translated-resume.epub"
        checkpoint_dir = Path(temp_dir) / "checkpoint"
        _build_two_chapter_epub(source_epub)

        first_call_count = 0

        def fail_on_second_doc(batch_text: str) -> str:
            nonlocal first_call_count
            first_call_count += 1
            if "Doc2" in batch_text:
                raise RuntimeError("simulated interruption")
            return f"R1:{batch_text}"

        with pytest.raises(RuntimeError, match="simulated interruption"):
            run_translate_roundtrip(
                source_epub=source_epub,
                output_epub=output_epub,
                output_lang="zh",
                bilingual_style="alternating",
                model="gemini-2.5-flash",
                custom_prompt=None,
                translate_fn=fail_on_second_doc,
                checkpoint_dir=checkpoint_dir,
            )

        assert first_call_count == 2

        second_call_count = 0

        def succeed_resume(batch_text: str) -> str:
            nonlocal second_call_count
            second_call_count += 1
            return f"R2:{batch_text}"

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=succeed_resume,
            checkpoint_dir=checkpoint_dir,
        )

        assert second_call_count == 1
        with zipfile.ZipFile(output_epub, "r") as output_zip:
            chapter1 = output_zip.read("chapter1.xhtml").decode("utf-8")
            chapter2 = output_zip.read("chapter2.xhtml").decode("utf-8")

        assert "R1:Doc1" in chapter1
        assert "R2:Doc2" in chapter2


def test_checkpoint_invalidated_when_context_signature_changes() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-context-change.epub"
        output_epub = Path(temp_dir) / "translated-context-change.epub"
        checkpoint_dir = Path(temp_dir) / "checkpoint"
        _build_two_chapter_epub(source_epub)

        first_call_count = 0

        def first_run_translate(batch_text: str) -> str:
            nonlocal first_call_count
            first_call_count += 1
            return f"R1:{batch_text}"

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=first_run_translate,
            checkpoint_dir=checkpoint_dir,
            context_max_paragraphs_per_doc=8,
            context_max_paragraphs_total=120,
        )
        assert first_call_count == 2

        second_call_count = 0

        def second_run_translate(batch_text: str) -> str:
            nonlocal second_call_count
            second_call_count += 1
            return f"R2:{batch_text}"

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=second_run_translate,
            checkpoint_dir=checkpoint_dir,
            context_max_paragraphs_per_doc=4,
            context_max_paragraphs_total=120,
        )

        assert second_call_count == 2


def test_force_context_rebuild_invalidates_checkpoint() -> None:
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    with tempfile.TemporaryDirectory() as temp_dir:
        source_epub = Path(temp_dir) / "book-force-rebuild.epub"
        output_epub = Path(temp_dir) / "translated-force-rebuild.epub"
        checkpoint_dir = Path(temp_dir) / "checkpoint"
        _build_two_chapter_epub(source_epub)

        initial_calls = 0

        def initial_translate(batch_text: str) -> str:
            nonlocal initial_calls
            initial_calls += 1
            return f"A:{batch_text}"

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=initial_translate,
            checkpoint_dir=checkpoint_dir,
        )
        assert initial_calls == 2

        rebuild_calls = 0

        def rebuild_translate(batch_text: str) -> str:
            nonlocal rebuild_calls
            rebuild_calls += 1
            return f"B:{batch_text}"

        run_translate_roundtrip(
            source_epub=source_epub,
            output_epub=output_epub,
            output_lang="zh",
            bilingual_style="alternating",
            model="gemini-2.5-flash",
            custom_prompt=None,
            translate_fn=rebuild_translate,
            checkpoint_dir=checkpoint_dir,
            force_context_rebuild=True,
        )

        assert rebuild_calls == 2


def test_epub_roundtrip_accepts_context_pass_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_roundtrip_cli_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "09_epub_translate_roundtrip.py",
            "book.epub",
            "--output",
            "translated.epub",
            "--context-pass-mode",
            "off",
            "--force-context-rebuild",
            "--context-max-paragraphs-per-doc",
            "10",
            "--context-max-paragraphs-total",
            "150",
        ],
    )

    args = module.parse_arguments()
    assert args.context_pass_mode == "off"
    assert args.force_context_rebuild is True
    assert args.context_max_paragraphs_per_doc == 10
    assert args.context_max_paragraphs_total == 150


def test_epub_roundtrip_accepts_audience_and_style_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_roundtrip_cli_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "09_epub_translate_roundtrip.py",
            "book.epub",
            "--output",
            "translated.epub",
            "--audience",
            "technical",
            "--style",
            "technical",
        ],
    )

    args = module.parse_arguments()
    assert args.audience == "technical"
    assert args.style == "technical"
