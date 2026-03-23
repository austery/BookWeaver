from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import zipfile

import pytest


def test_read_zip_text_missing_entry_raises_value_error() -> None:
    import io
    import zipfile
    from ai.epub_translate_roundtrip import _read_zip_text

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("real_file.xhtml", "<html/>")
    buf.seek(0)

    with zipfile.ZipFile(buf, "r") as zf:
        with pytest.raises(ValueError, match="EPUB missing required file"):
            _read_zip_text(zf, "does_not_exist.xhtml")


def test_checkpoint_mismatch_prints_warning(tmp_path: Path, capsys) -> None:
    import json
    from ai.epub_translate_roundtrip import _load_checkpoint_snapshot

    # _checkpoint_state_file(checkpoint_dir) returns checkpoint_dir / "state.json"
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "source_signature": "abc123",
                "output_lang": "zh",
                "bilingual_style": "alternating",
                "model": "gemini-2.5-flash",  # ← will differ from call argument
                "custom_prompt": None,
                "completed_docs": [],
            }
        ),
        encoding="utf-8",
    )

    # Call with a different model — should trigger mismatch warning
    _load_checkpoint_snapshot(
        checkpoint_dir=tmp_path,  # ← correct parameter name
        source_signature="abc123",
        output_lang="zh",
        bilingual_style="alternating",
        model="gemini-2.5-pro",  # ← different from checkpoint
        custom_prompt=None,
    )

    captured = capsys.readouterr()
    assert "[WARN]" in captured.out
    assert "Checkpoint invalidated" in captured.out


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
