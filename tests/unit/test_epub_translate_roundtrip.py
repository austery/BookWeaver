from __future__ import annotations

import subprocess
import tempfile
import zipfile
from pathlib import Path

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


def test_checkpoint_mismatch_prints_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
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


def test_checkpoint_model_change_with_force_resume(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that force_resume allows resuming with different model."""
    import json
    from ai.epub_translate_roundtrip import _load_checkpoint_snapshot

    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "source_signature": "abc123",
                "output_lang": "zh",
                "bilingual_style": "alternating",
                "model": "gemini-2.5-flash",
                "custom_prompt": None,
                "completed_docs": [
                    {
                        "doc_path": "chapter1.xhtml",
                        "checkpoint_file": "abc.xhtml",
                        "segments": 5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    # Create checkpoint doc file
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "abc.xhtml").write_text("<html/>", encoding="utf-8")

    # Call with force_resume=True and different model
    snapshot = _load_checkpoint_snapshot(
        checkpoint_dir=tmp_path,
        source_signature="abc123",
        output_lang="zh",
        bilingual_style="alternating",
        model="gemini-3-pro-preview",  # different model
        custom_prompt=None,
        force_resume=True,
    )

    # Should NOT invalidate checkpoint
    assert len(snapshot.entries) == 1
    assert "chapter1.xhtml" in snapshot.entries
    assert snapshot.translated_docs == 1
    assert snapshot.translated_segments == 5

    # Should print warning about force-resume
    captured = capsys.readouterr()
    assert "[WARN]" in captured.out
    assert "force-resume enabled" in captured.out
    assert "Checkpoint invalidated" not in captured.out


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


def test_plan_segment_batches_enforces_char_limit_and_order() -> None:
    from ai.epub_translate_roundtrip import plan_segment_batches

    # Each segment is ~500 chars; 60K limit → batches of ~120 segments
    segments = [f"S{i}-" + ("x" * 500) for i in range(130)]
    batches = plan_segment_batches(
        segments,
        max_batch_chars=60_000,
    )

    # All segments preserved in order
    assert [item for batch in batches for item in batch] == segments
    # No batch exceeds char limit (except a single oversized segment)
    sep_len = len("\n\n%%\n\n")
    for batch in batches:
        joined_len = sum(len(s) for s in batch) + sep_len * (len(batch) - 1)
        assert joined_len <= 60_000 or len(batch) == 1


def test_plan_segment_batches_allows_single_oversized_segment() -> None:
    from ai.epub_translate_roundtrip import plan_segment_batches

    oversized = "y" * 30_000
    batches = plan_segment_batches(
        [oversized, "ok"],
        max_batch_chars=18_000,
    )

    assert len(batches) == 2
    assert batches[0] == [oversized]
    assert batches[1] == ["ok"]


def test_plan_segment_batches_many_short_segments_stay_in_few_batches() -> None:
    """812 short segments (like index.xhtml) must not create 23 batches."""
    from ai.epub_translate_roundtrip import plan_segment_batches

    segments = ["word" * 25 for _ in range(812)]  # ~100 chars each, 81K total
    batches = plan_segment_batches(segments, max_batch_chars=60_000)

    # Must be at most 2 batches (81K / 60K = 2), NOT 23
    assert len(batches) <= 2
    assert sum(len(b) for b in batches) == 812


def test_plan_segment_batches_short_segments_within_limit_are_one_batch() -> None:
    from ai.epub_translate_roundtrip import plan_segment_batches

    # 200 segments × 10 chars each = 2000 chars total — well within 60K
    segments = ["hello-ok!!" for _ in range(200)]
    batches = plan_segment_batches(segments, max_batch_chars=60_000)

    assert len(batches) == 1
    assert batches[0] == segments


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
        # 130 paragraphs × ~500 chars = ~65K total → exceeds 60K char limit → 2 batches
        paragraphs = [f"P{i}-" + ("x" * 500) for i in range(130)]
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

        # 130 × ~504 chars ≈ 65K > 60K limit → must split into multiple batches
        assert len(calls) > 1
        # Each batch must stay within the 60K char limit (excluding single-segment overflow)
        sep = "\n\n%%\n\n"
        for payload in calls:
            assert len(payload) <= 60_000 or sep not in payload


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


def test_rate_limit_retry_sleeps_then_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """On RateLimitError, function sleeps using first backoff slot then retries."""
    import time
    from ai.epub_translate_roundtrip import translate_segments_with_batch_retry
    from ai.gemini_provider import RateLimitError

    sleep_calls: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleep_calls.append(s))

    call_count = 0

    def flaky_translate(text: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # fail only once — consumes backoff[0]=60
            raise RateLimitError("rate limited")
        return f"ZH:{text}"

    result = translate_segments_with_batch_retry(
        ["hello"],
        translate_batch=flaky_translate,
        context_label="test",
    )
    assert result == ["ZH:hello"]
    assert sleep_calls == [60]  # first backoff slot used


def test_rate_limit_retry_uses_retry_after_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    """When RateLimitError carries retry_after_seconds, that value is used instead of backoff."""
    import time
    from ai.epub_translate_roundtrip import translate_segments_with_batch_retry
    from ai.gemini_provider import RateLimitError

    sleep_calls: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleep_calls.append(s))

    call_count = 0

    def flaky_translate(text: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RateLimitError("rate limited", retry_after_seconds=45)
        return f"ZH:{text}"

    translate_segments_with_batch_retry(
        ["hello"],
        translate_batch=flaky_translate,
        context_label="test",
    )
    assert sleep_calls == [45]  # uses retry_after, not 60


def test_rate_limit_retry_exhausted_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """After both backoff slots consumed, RateLimitError propagates. Both sleep values are used."""
    import time
    from ai.epub_translate_roundtrip import translate_segments_with_batch_retry
    from ai.gemini_provider import RateLimitError

    sleep_calls: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleep_calls.append(s))

    def always_rate_limited(text: str) -> str:
        raise RateLimitError("always limited")

    with pytest.raises(RateLimitError):
        translate_segments_with_batch_retry(
            ["hello"],
            translate_batch=always_rate_limited,
            context_label="test",
        )
    # Both backoff slots are consumed (60s then 120s) before giving up
    assert sleep_calls == [60, 120]


def test_rate_limit_does_not_trigger_split(monkeypatch: pytest.MonkeyPatch) -> None:
    """RateLimitError retries the SAME batch, not a split sub-batch."""
    import time
    from ai.epub_translate_roundtrip import translate_segments_with_batch_retry
    from ai.gemini_provider import RateLimitError

    monkeypatch.setattr(time, "sleep", lambda s: None)

    received_lengths: list[int] = []

    def track_and_fail(text: str) -> str:
        # Count segments by separator count
        count = text.count("%%") + 1 if "%%" in text else 1
        received_lengths.append(count)
        if len(received_lengths) == 1:  # fail only once — one backoff slot consumed
            raise RateLimitError("limited")
        return "\n\n%%\n\n".join(f"ZH:{i}" for i in range(count))

    translate_segments_with_batch_retry(
        [f"seg{i}" for i in range(4)],
        translate_batch=track_and_fail,
        context_label="test",
    )
    # All calls should be for 4 segments (same batch), never 2+2 split
    assert all(n == 4 for n in received_lengths)


def test_pro_timeout_passed_to_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """batch_translate closure passes timeout_seconds=300 for Pro model."""
    import tempfile
    from pathlib import Path
    from ai import gemini_provider
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    received_timeout: list[int] = []

    def capture_translate(
        self: object,  # instance — required for class-level monkeypatch
        text: str,
        chunk_size: int,
        system_prompt: str,
        timeout_seconds: int = 180,
    ) -> str:
        received_timeout.append(timeout_seconds)
        count = text.count("%%") + 1 if "%%" in text else 1
        return "\n\n%%\n\n".join("ZH:seg" for _ in range(count))

    monkeypatch.setattr(gemini_provider.GeminiProvider, "translate_chunk", capture_translate)

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "book.epub"
        out = Path(tmp) / "out.epub"
        _build_min_epub(src)

        run_translate_roundtrip(
            source_epub=src,
            output_epub=out,
            output_lang="zh",
            bilingual_style="alternating",
            model="pro",  # resolves to _MODEL_ALIASES["pro"] = "gemini-3-pro-preview"
        )

    assert received_timeout and all(t == 300 for t in received_timeout)


def test_api_provider_timeout_passed_to_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """batch_translate closure passes timeout_seconds=180 for API provider."""
    import tempfile
    from pathlib import Path

    from ai import gemini_api_provider
    from ai.epub_translate_roundtrip import run_translate_roundtrip

    received_timeout: list[int] = []

    def capture_translate(
        self: object,
        text: str,
        chunk_size: int,
        system_prompt: str,
        timeout_seconds: int = 180,
    ) -> str:
        received_timeout.append(timeout_seconds)
        count = text.count("%%") + 1 if "%%" in text else 1
        return "\n\n%%\n\n".join("ZH:seg" for _ in range(count))

    monkeypatch.setattr(gemini_api_provider.GeminiAPIProvider, "translate_chunk", capture_translate)

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "book.epub"
        out = Path(tmp) / "out.epub"
        _build_min_epub(src)

        run_translate_roundtrip(
            source_epub=src,
            output_epub=out,
            output_lang="zh",
            bilingual_style="alternating",
            model="flash",
            provider_name="api",
            api_key="test-key",
        )

    assert received_timeout and all(t == 180 for t in received_timeout)
