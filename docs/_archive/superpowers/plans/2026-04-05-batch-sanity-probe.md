# Batch Sanity Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lightweight per-batch guard to `ai/cli.py` that halts the pipeline on empty output, runaway length ratios, or wrong-language (non-CJK) output, and emits a one-line heartbeat sample after every batch.

**Architecture:** All logic lives in `ai/cli.py` (the composition root). Three new module-level helpers (`_SanityProbeConfig`, `_sanity_check_batch`, `_emit_batch_sample`) are wired into `run()` via the existing `on_checkpoint_batch` callback. The callback is now always created when the probe is enabled (even without resume), using a `_persist_fn` inner slot for optional checkpoint persistence.

**Tech Stack:** Python stdlib only (`dataclasses`, `unicodedata` range check). No new dependencies.

---

## File Map

| File | Change |
|---|---|
| `ai/cli.py` | Add `_SanityProbeConfig`, `_load_probe_config`, `_count_cjk`, `_sanity_check_batch`, `_emit_batch_sample`; restructure callback in `run()`; add `no_sanity_probe` param; add `--no-sanity-probe` arg |
| `config/config.json.example` | Add `sanity_probe` top-level key |
| `tests/unit/test_cli.py` | Add `TestSanityProbe` class with 7 tests |

---

## Task 1: `_SanityProbeConfig` dataclass + `_load_probe_config`

**Files:**
- Modify: `ai/cli.py` — add after the existing `_CHECKPOINT_TRANSLATIONS_FILE` constant block (around line 85)

- [ ] **Step 1.1: Write the failing test**

Add this class to `tests/unit/test_cli.py` after the `TestBuildSystemPrompt` section:

```python
class TestSanityProbeConfig:
    def test_load_probe_config_defaults(self) -> None:
        from ai.cli import _load_probe_config
        cfg = _load_probe_config({})
        assert cfg.enabled is True
        assert cfg.max_length_ratio == 2.0
        assert cfg.min_length_ratio == 0.15
        assert cfg.min_source_length == 10
        assert cfg.min_cjk_density == 0.30
        assert cfg.heartbeat_chars == 60

    def test_load_probe_config_from_dict(self) -> None:
        from ai.cli import _load_probe_config
        cfg = _load_probe_config({"sanity_probe": {
            "enabled": False,
            "max_length_ratio": 3.0,
            "min_length_ratio": 0.1,
            "min_source_length": 5,
            "min_cjk_density": 0.5,
            "heartbeat_chars": 80,
        }})
        assert cfg.enabled is False
        assert cfg.max_length_ratio == 3.0
        assert cfg.min_cjk_density == 0.5

    def test_load_probe_config_ignores_bad_type(self) -> None:
        from ai.cli import _load_probe_config
        cfg = _load_probe_config({"sanity_probe": "not-a-dict"})
        assert cfg.enabled is True  # falls back to defaults
```

- [ ] **Step 1.2: Run to verify failure**

```bash
cd /Users/leipeng/Documents/Projects/BookWeaver
uv run pytest tests/unit/test_cli.py::TestSanityProbeConfig -v 2>&1 | tail -15
```
Expected: `ImportError` or `AttributeError` — `_load_probe_config` not yet defined.

- [ ] **Step 1.3: Implement**

In `ai/cli.py`, add after the line `_DEFAULT_BATCH_CHARS_STANDARD_EPUB = 60_000` (around line 85):

```python
# ── Sanity probe ──────────────────────────────────────────────


@dataclass(frozen=True)
class _SanityProbeConfig:
    enabled: bool = True
    max_length_ratio: float = 2.0
    min_length_ratio: float = 0.15
    min_source_length: int = 10
    min_cjk_density: float = 0.30
    heartbeat_chars: int = 60


def _load_probe_config(runtime_config: dict[str, object]) -> _SanityProbeConfig:
    raw = runtime_config.get("sanity_probe", {})
    if not isinstance(raw, dict):
        return _SanityProbeConfig()
    return _SanityProbeConfig(
        enabled=bool(raw.get("enabled", True)),
        max_length_ratio=float(raw.get("max_length_ratio", 2.0)),
        min_length_ratio=float(raw.get("min_length_ratio", 0.15)),
        min_source_length=int(raw.get("min_source_length", 10)),
        min_cjk_density=float(raw.get("min_cjk_density", 0.30)),
        heartbeat_chars=int(raw.get("heartbeat_chars", 60)),
    )
```

- [ ] **Step 1.4: Run to verify pass**

```bash
uv run pytest tests/unit/test_cli.py::TestSanityProbeConfig -v 2>&1 | tail -10
```
Expected: `3 passed`.

- [ ] **Step 1.5: Commit**

```bash
git add ai/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add _SanityProbeConfig dataclass and _load_probe_config

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: `_count_cjk` + `_sanity_check_batch`

**Files:**
- Modify: `ai/cli.py` — add after `_load_probe_config`

- [ ] **Step 2.1: Write the failing tests**

Add to the `TestSanityProbeConfig` class (or a new `TestSanityCheckBatch` class):

```python
class TestSanityCheckBatch:
    def _make_seg(self, seg_id: str, original: str, translated: str) -> TranslatedSegment:
        return TranslatedSegment(id=seg_id, original=original, translated=translated)

    def _default_probe(self) -> "_SanityProbeConfig":
        from ai.cli import _SanityProbeConfig
        return _SanityProbeConfig()

    def test_passes_normal_en_to_zh(self) -> None:
        from ai.cli import _sanity_check_batch
        segs = [self._make_seg("ch1.xhtml::0", "The key principle is", "核心原则是")]
        # Should not raise
        _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=0, total_batches=5)

    def test_raises_on_empty_output(self) -> None:
        from ai.cli import _sanity_check_batch
        from ai.ports.provider import TranslationError
        segs = [self._make_seg("ch1.xhtml::0", "Hello world", "")]
        with pytest.raises(TranslationError, match="empty output"):
            _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=2, total_batches=10)

    def test_raises_on_length_ratio_too_high(self) -> None:
        from ai.cli import _sanity_check_batch
        from ai.ports.provider import TranslationError
        # Source 20 chars, translated 200 chars (ratio=10.0 > max=2.0)
        segs = [self._make_seg("ch1.xhtml::0", "Hello world example.", "你" * 200)]
        with pytest.raises(TranslationError, match="length_ratio"):
            _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=0, total_batches=1)

    def test_raises_on_cjk_density_too_low(self) -> None:
        from ai.cli import _sanity_check_batch
        from ai.ports.provider import TranslationError
        # Source 20 chars, translated is pure English (density=0.0 < 0.30)
        segs = [self._make_seg("ch1.xhtml::0", "Hello world example.", "Hello world example.")]
        with pytest.raises(TranslationError, match="cjk_density"):
            _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=1, total_batches=5)

    def test_skips_length_ratio_for_short_source(self) -> None:
        from ai.cli import _sanity_check_batch
        # Source only 3 chars (< min_source_length=10), translated is long — should NOT raise
        segs = [self._make_seg("ch1.xhtml::0", "A", "翻译一下这个字母A的中文意思是什么")]
        _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=0, total_batches=1)

    def test_skips_cjk_check_for_non_zh_lang(self) -> None:
        from ai.cli import _sanity_check_batch
        # Non-zh output lang, translated is pure English — should NOT raise on CJK check
        segs = [self._make_seg("ch1.xhtml::0", "Hello world example.", "Hallo Welt Beispiel.")]
        _sanity_check_batch(segs, "de", self._default_probe(), batch_index=0, total_batches=1)

    def test_error_message_includes_batch_position(self) -> None:
        from ai.cli import _sanity_check_batch
        from ai.ports.provider import TranslationError
        segs = [self._make_seg("ch1.xhtml::5", "Hello world.", "")]
        with pytest.raises(TranslationError, match=r"batch 3/10"):
            _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=2, total_batches=10)
```

- [ ] **Step 2.2: Run to verify failure**

```bash
uv run pytest tests/unit/test_cli.py::TestSanityCheckBatch -v 2>&1 | tail -15
```
Expected: `ImportError` — `_sanity_check_batch` not yet defined.

- [ ] **Step 2.3: Implement**

In `ai/cli.py`, add after `_load_probe_config`:

```python
def _count_cjk(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def _sanity_check_batch(
    translated: list[TranslatedSegment],
    output_lang: str,
    probe_config: _SanityProbeConfig,
    batch_index: int,
    total_batches: int,
) -> None:
    check_cjk = output_lang.startswith("zh")
    batch_label = f"{batch_index + 1}/{total_batches}"
    for seg in translated:
        tgt = seg.translated
        src = seg.original
        if not tgt.strip():
            raise TranslationError(
                f"sanity check failed at batch {batch_label} — empty output (segment {seg.id})"
            )
        if len(src) >= probe_config.min_source_length:
            ratio = len(tgt) / len(src)
            if ratio < probe_config.min_length_ratio or ratio > probe_config.max_length_ratio:
                raise TranslationError(
                    f"sanity check failed at batch {batch_label} — "
                    f"length_ratio={ratio:.2f} not in "
                    f"[{probe_config.min_length_ratio}, {probe_config.max_length_ratio}]"
                    f" (segment {seg.id})"
                )
        if check_cjk:
            cjk_count = _count_cjk(tgt)
            density = cjk_count / len(tgt)
            if density < probe_config.min_cjk_density:
                raise TranslationError(
                    f"sanity check failed at batch {batch_label} — "
                    f"cjk_density={density:.2f} < {probe_config.min_cjk_density}"
                    f" (segment {seg.id})"
                )
```

- [ ] **Step 2.4: Run to verify pass**

```bash
uv run pytest tests/unit/test_cli.py::TestSanityCheckBatch -v 2>&1 | tail -15
```
Expected: `7 passed`.

- [ ] **Step 2.5: Commit**

```bash
git add ai/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add _sanity_check_batch with empty/ratio/CJK guards

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: `_emit_batch_sample`

**Files:**
- Modify: `ai/cli.py` — add after `_sanity_check_batch`

- [ ] **Step 3.1: Write the failing test**

Add to `tests/unit/test_cli.py`:

```python
class TestEmitBatchSample:
    def test_emits_batch_sample_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        from ai.cli import _emit_batch_sample, _SanityProbeConfig
        segs = [
            TranslatedSegment(
                id="EPUB/ch04.xhtml::0",
                original="The key principle is encapsulation of state.",
                translated="核心原则是状态封装。",
            )
        ]
        _emit_batch_sample(segs, _SanityProbeConfig(), batch_index=2, total_batches=10)
        out = capsys.readouterr().out
        assert "[progress:batch_sample]" in out
        assert "batch=3/10" in out
        assert "doc=EPUB/ch04.xhtml" in out
        assert "核心原则" in out

    def test_truncates_long_source(self, capsys: pytest.CaptureFixture[str]) -> None:
        from ai.cli import _emit_batch_sample, _SanityProbeConfig
        long_src = "A" * 200
        long_tgt = "中" * 200
        segs = [TranslatedSegment(id="ch::0", original=long_src, translated=long_tgt)]
        _emit_batch_sample(segs, _SanityProbeConfig(heartbeat_chars=60), batch_index=0, total_batches=1)
        out = capsys.readouterr().out
        assert "..." in out

    def test_no_output_for_empty_batch(self, capsys: pytest.CaptureFixture[str]) -> None:
        from ai.cli import _emit_batch_sample, _SanityProbeConfig
        _emit_batch_sample([], _SanityProbeConfig(), batch_index=0, total_batches=1)
        out = capsys.readouterr().out
        assert "[progress:batch_sample]" not in out
```

- [ ] **Step 3.2: Run to verify failure**

```bash
uv run pytest tests/unit/test_cli.py::TestEmitBatchSample -v 2>&1 | tail -10
```
Expected: `ImportError` — `_emit_batch_sample` not yet defined.

- [ ] **Step 3.3: Implement**

In `ai/cli.py`, add after `_sanity_check_batch`:

```python
def _emit_batch_sample(
    translated: list[TranslatedSegment],
    probe_config: _SanityProbeConfig,
    batch_index: int,
    total_batches: int,
) -> None:
    if not translated:
        return
    first = translated[0]
    doc_path = first.id.split("::")[0] if "::" in first.id else None
    n = probe_config.heartbeat_chars
    src = first.original
    tgt = first.translated
    src_snippet = src[:n] + ("..." if len(src) > n else "")
    tgt_snippet = tgt[:n] + ("..." if len(tgt) > n else "")
    _log_progress(
        "batch_sample",
        batch=f"{batch_index + 1}/{total_batches}",
        doc=doc_path,
        src=src_snippet,
        tgt=tgt_snippet,
    )
```

- [ ] **Step 3.4: Run to verify pass**

```bash
uv run pytest tests/unit/test_cli.py::TestEmitBatchSample -v 2>&1 | tail -10
```
Expected: `3 passed`.

- [ ] **Step 3.5: Commit**

```bash
git add ai/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add _emit_batch_sample heartbeat per batch

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: Wire probe into `run()` callback

**Files:**
- Modify: `ai/cli.py` — restructure the callback block in `run()` and add `no_sanity_probe` param

- [ ] **Step 4.1: Write the failing integration tests**

Add to `tests/unit/test_cli.py`:

```python
class TestRunSanityProbe:
    """Tests that run() wires the sanity probe into the on_checkpoint_batch callback."""

    def _patch_base(
        self,
        monkeypatch: pytest.MonkeyPatch,
        source: _ResumeSource,
        provider: _ResumeProvider,
    ) -> None:
        monkeypatch.setattr(cli_module, "load_config", lambda: {})
        monkeypatch.setattr(
            cli_module,
            "resolve_model",
            lambda model, config, *, explicit=False: ("gemini-2.5-flash", False),
        )
        monkeypatch.setattr(cli_module, "create_provider", lambda *args, **kwargs: provider)
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: source)

    def test_run_emits_batch_sample_lines(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = _ResumeSource()
        provider = _ResumeProvider()
        self._patch_base(monkeypatch, source, provider)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")

        run(input_path=str(in_epub), output=str(tmp_path / "out.epub"), input_format="epub")

        out = capsys.readouterr().out
        # One heartbeat per batch (2 batches from _ResumeSource)
        assert out.count("[progress:batch_sample]") == 2

    def test_run_halts_on_empty_translation(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _EmptyProvider:
            def translate_batch(self, segments: list[str], *, system_prompt: str) -> list[str]:
                return [""] * len(segments)

        source = _ResumeSource()
        provider = _EmptyProvider()
        self._patch_base(monkeypatch, source, provider)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")

        with pytest.raises(TranslationError, match="empty output"):
            run(input_path=str(in_epub), output=str(tmp_path / "out.epub"), input_format="epub")

    def test_no_sanity_probe_flag_suppresses_probe_and_sample(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        class _EmptyProvider:
            def translate_batch(self, segments: list[str], *, system_prompt: str) -> list[str]:
                return [""] * len(segments)

        source = _ResumeSource()
        provider = _EmptyProvider()
        self._patch_base(monkeypatch, source, provider)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")

        # With probe disabled, empty output should NOT raise
        run(
            input_path=str(in_epub),
            output=str(tmp_path / "out.epub"),
            input_format="epub",
            no_sanity_probe=True,
        )

        out = capsys.readouterr().out
        assert "[progress:batch_sample]" not in out

    def test_probe_disabled_via_config(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        class _EmptyProvider:
            def translate_batch(self, segments: list[str], *, system_prompt: str) -> list[str]:
                return [""] * len(segments)

        source = _ResumeSource()
        provider = _EmptyProvider()
        monkeypatch.setattr(
            cli_module, "load_config",
            lambda: {"sanity_probe": {"enabled": False}},
        )
        monkeypatch.setattr(
            cli_module,
            "resolve_model",
            lambda model, config, *, explicit=False: ("gemini-2.5-flash", False),
        )
        monkeypatch.setattr(cli_module, "create_provider", lambda *args, **kwargs: provider)
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: source)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")

        run(
            input_path=str(in_epub),
            output=str(tmp_path / "out.epub"),
            input_format="epub",
        )

        out = capsys.readouterr().out
        assert "[progress:batch_sample]" not in out
```

- [ ] **Step 4.2: Run to verify failure**

```bash
uv run pytest tests/unit/test_cli.py::TestRunSanityProbe -v 2>&1 | tail -15
```
Expected: `TypeError` — `run()` doesn't accept `no_sanity_probe` yet; empty provider tests pass without error.

- [ ] **Step 4.3: Implement — restructure `run()` callback block**

In `ai/cli.py`, make these changes:

**Change 1:** Add `no_sanity_probe: bool = False` to `run()` signature — add it after `checkpoint_dir: str | None = None`:

```python
    checkpoint_dir: str | None = None,
    no_sanity_probe: bool = False,
    model_explicit: bool = False,
```

**Change 2:** Replace the entire block from `resume_translations: dict[str, str] | None = None` through `checkpoint_callback = _persist_batch` (the current end of the resume block, around line 836–886) with:

```python
        resume_translations: dict[str, str] | None = None
        _persist_fn: Callable[[int, list[TranslatedSegment]], None] | None = None
        resume_enabled = resume or force_resume
        if resume_enabled:
            if fmt != "epub":
                print("Warning: Resume is only supported for EPUB input; ignoring resume flags.")
                _log_progress("resume", enabled=False, reason="non-epub")
            else:
                checkpoint_path = _resolve_checkpoint_dir(
                    checkpoint_dir=checkpoint_dir,
                    input_file=input_file,
                    output_file=Path(output),
                    input_format=fmt,
                )
                checkpoint_metadata = _build_checkpoint_metadata(
                    input_file=input_file,
                    input_format=fmt,
                    output_lang=output_lang,
                    model=resolved_model,
                    provider=provider,
                    max_batch_chars=batch_chars,
                    separator_overhead=SEPARATOR_OVERHEAD,
                    system_prompt=system_prompt,
                )
                resume_translations = _load_checkpoint_translations(
                    checkpoint_dir=checkpoint_path,
                    metadata=checkpoint_metadata,
                    force_resume=force_resume,
                )
                _log_progress(
                    "resume",
                    checkpoint=checkpoint_path,
                    restored_segments=len(resume_translations),
                    force=force_resume,
                )

                persisted_translations = dict(resume_translations)

                def _persist(
                    _batch_index: int, translated: list[TranslatedSegment]
                ) -> None:
                    for item in translated:
                        persisted_translations[item.id] = item.translated
                    _persist_checkpoint(
                        checkpoint_dir=checkpoint_path,
                        metadata=checkpoint_metadata,
                        translations=persisted_translations,
                    )

                _persist_fn = _persist

        probe_config = _load_probe_config(runtime_config)
        if no_sanity_probe:
            probe_config = _SanityProbeConfig(enabled=False)

        _total_batches: list[int] = [0]
        checkpoint_callback: Callable[[int, list[TranslatedSegment]], None] | None = None
        if probe_config.enabled or _persist_fn is not None:

            def _on_checkpoint_batch(
                batch_index: int, translated: list[TranslatedSegment]
            ) -> None:
                if probe_config.enabled:
                    _sanity_check_batch(
                        translated, output_lang, probe_config, batch_index, _total_batches[0]
                    )
                    _emit_batch_sample(translated, probe_config, batch_index, _total_batches[0])
                if _persist_fn is not None:
                    _persist_fn(batch_index, translated)

            checkpoint_callback = _on_checkpoint_batch
```

**Change 3:** In `_on_source_loaded` (already defined just before `engine.translate`), capture `total_batches`:

Replace:
```python
        def _on_source_loaded(
            total_segments: int, resumed_segments: int, total_batches: int
        ) -> None:
            _log_progress(
                "source",
                format=fmt,
                segments=total_segments,
                resumed=resumed_segments,
                pending=max(total_segments - resumed_segments, 0),
                batches=total_batches,
            )
```

With:
```python
        def _on_source_loaded(
            total_segments: int, resumed_segments: int, total_batches: int
        ) -> None:
            _total_batches[0] = total_batches
            _log_progress(
                "source",
                format=fmt,
                segments=total_segments,
                resumed=resumed_segments,
                pending=max(total_segments - resumed_segments, 0),
                batches=total_batches,
            )
```

- [ ] **Step 4.4: Run to verify pass**

```bash
uv run pytest tests/unit/test_cli.py::TestRunSanityProbe -v 2>&1 | tail -15
```
Expected: `4 passed`.

- [ ] **Step 4.5: Run full test suite to verify no regressions**

```bash
uv run pytest tests/unit/test_cli.py -q 2>&1 | tail -15
```
Expected: all tests pass (look for `N passed`, 0 failed).

- [ ] **Step 4.6: Commit**

```bash
git add ai/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): wire sanity probe into run() on_checkpoint_batch callback

- Always creates on_checkpoint_batch when probe enabled (not just on resume)
- Probe runs: check → heartbeat → persist (if resume enabled)
- _total_batches captured from _on_source_loaded for heartbeat formatting
- no_sanity_probe=True param disables all checks and heartbeat

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: `--no-sanity-probe` CLI flag + wire through `main()`

**Files:**
- Modify: `ai/cli.py` — `build_parser()` and `main()`

- [ ] **Step 5.1: Write the failing test**

Add to `tests/unit/test_cli.py` inside `TestBuildParser` class (or after it):

```python
class TestNoSanityProbeFlag:
    def test_no_sanity_probe_flag_present_in_parser(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["input.epub", "--output", "out.epub", "--no-sanity-probe"])
        assert args.no_sanity_probe is True

    def test_no_sanity_probe_defaults_to_false(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["input.epub", "--output", "out.epub"])
        assert args.no_sanity_probe is False
```

- [ ] **Step 5.2: Run to verify failure**

```bash
uv run pytest tests/unit/test_cli.py::TestNoSanityProbeFlag -v 2>&1 | tail -10
```
Expected: `SystemExit` or `error: unrecognized arguments`.

- [ ] **Step 5.3: Implement**

**In `build_parser()`:** add the flag after the existing `--checkpoint-dir` argument block:

```python
    parser.add_argument(
        "--no-sanity-probe",
        action="store_true",
        default=False,
        help="Disable per-batch sanity checks and heartbeat sample output.",
    )
```

**In `main()`:** add `no_sanity_probe=args.no_sanity_probe` to the `run(...)` call:

```python
    run(
        input_path=args.input_path,
        output=args.output,
        output_lang=args.output_lang,
        model=args.model,
        model_explicit=model_explicit,
        provider=args.provider,
        prompt=args.prompt,
        extract_glossary=args.extract_glossary,
        glossary=args.glossary,
        glossary_min_priority=args.glossary_min_priority,
        glossary_max_terms=args.glossary_max_terms,
        cli_api_fallback=args.cli_api_fallback,
        max_batch_chars=args.max_batch_chars,
        input_format=args.input_format,
        resume=args.resume,
        force_resume=args.force_resume,
        checkpoint_dir=args.checkpoint_dir,
        no_sanity_probe=args.no_sanity_probe,
    )
```

- [ ] **Step 5.4: Run to verify pass**

```bash
uv run pytest tests/unit/test_cli.py::TestNoSanityProbeFlag -v 2>&1 | tail -10
```
Expected: `2 passed`.

- [ ] **Step 5.5: Commit**

```bash
git add ai/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add --no-sanity-probe CLI flag

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: Update `config/config.json.example`

**Files:**
- Modify: `config/config.json.example` — add `sanity_probe` top-level key

- [ ] **Step 6.1: Add `sanity_probe` block**

In `config/config.json.example`, add before the final closing `}`:

```json
  "sanity_probe": {
    "enabled": true,
    "max_length_ratio": 2.0,
    "min_length_ratio": 0.15,
    "min_source_length": 10,
    "min_cjk_density": 0.30,
    "heartbeat_chars": 60
  }
```

(Add a comma after the previous last key `"terminology_extraction": { ... }` block.)

- [ ] **Step 6.2: Verify config is valid JSON**

```bash
python3 -c "import json; json.load(open('config/config.json.example')); print('valid JSON')"
```
Expected: `valid JSON`.

- [ ] **Step 6.3: Run full test suite**

```bash
uv run pytest -q 2>&1 | tail -10
```
Expected: all existing tests pass, 0 failures.

- [ ] **Step 6.4: Commit**

```bash
git add config/config.json.example
git commit -m "config: add sanity_probe defaults to config.json.example

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Self-Review Against SPEC-016

| Spec requirement | Task |
|---|---|
| Empty output check | Task 2 |
| Length ratio check (0.15–2.0, skip < 10 source chars) | Task 2 |
| CJK density check ≥ 0.30 (zh only) | Task 2 |
| Heartbeat `[progress:batch_sample]` per batch | Task 3 |
| Execution order: check → heartbeat → persist | Task 4 |
| Empty check before CJK density (no div-by-zero) | Task 2 (empty raises before density runs) |
| Always runs (not just on resume) | Task 4 |
| `--no-sanity-probe` suppresses all checks + heartbeat | Task 5 |
| `"enabled": false` in config suppresses all checks + heartbeat | Task 4 |
| `sanity_probe` in `config.json.example` | Task 6 |
| `TranslationError` includes batch position + segment id | Task 2 |
| Checkpoint preserves prior batches on failure | Inherited — probe raises before `_persist_fn`, and prior batches already written |

All spec requirements covered. No placeholders. Method names consistent across tasks.
