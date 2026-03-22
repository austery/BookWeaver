from __future__ import annotations

import json
from pathlib import Path

from ai.orchestrator import run_orchestrated_translation


def test_orchestrator_prompt_only_generates_analysis_and_prompt_without_outputs(
    tmp_path: Path,
) -> None:
    def should_not_translate(_: str, __: str) -> str:
        raise AssertionError("translate_fn should not be called in prompt-only phase")

    pages = {"page0001.md": "Source paragraph with Stoicism."}
    result = run_orchestrated_translation(
        temp_dir=tmp_path,
        pages=pages,
        output_lang="zh",
        translate_fn=should_not_translate,
        phase="prompt-only",
    )

    orchestration_dir = tmp_path / "orchestration"
    assert (orchestration_dir / "01-analysis.md").exists()
    assert (orchestration_dir / "02-prompt.md").exists()
    assert not (orchestration_dir / "04-critique.md").exists()
    assert not (orchestration_dir / "05-revision.md").exists()
    assert not (orchestration_dir / "06-polish.md").exists()
    assert (tmp_path / "orchestration" / "01-analysis.md").exists()
    assert (tmp_path / "orchestration" / "02-prompt.md").exists()
    assert result == {}

    metrics = json.loads((orchestration_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["mode"] == "orchestrated"
    assert metrics["phase"] == "prompt-only"
    assert metrics["pages"] == 1


def test_orchestrator_translate_phase_uses_generated_prompt_for_each_page(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    def fake_translate(text: str, prompt: str) -> str:
        calls.append((text, prompt))
        return f"translated::{text}"

    pages = {
        "page0001.md": "First source page.",
        "page0002.md": "Second source page.",
    }
    result = run_orchestrated_translation(
        temp_dir=tmp_path,
        pages=pages,
        output_lang="zh",
        custom_prompt="Prefer concise style.",
        translate_fn=fake_translate,
        phase="translate",
    )

    orchestration_dir = tmp_path / "orchestration"
    prompt_text = (orchestration_dir / "02-prompt.md").read_text(encoding="utf-8")
    assert "## Content Background" in prompt_text
    assert "## Translation Principles" in prompt_text
    assert "## Additional Instructions" in prompt_text
    assert len(calls) == 2
    assert all(call_prompt == prompt_text for _, call_prompt in calls)
    assert result == {
        "page0001.md": "translated::First source page.",
        "page0002.md": "translated::Second source page.",
    }
    assert (tmp_path / "orchestration" / "04-critique.md").exists()
    assert (tmp_path / "orchestration" / "05-revision.md").exists()
    assert (tmp_path / "orchestration" / "06-polish.md").exists()


def test_orchestrator_retries_transient_translate_errors(tmp_path: Path) -> None:
    attempts = 0

    def flaky_translate(_: str, __: str) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("transient abort")
        return "<!-- START -->\n最终成功\n<!-- END -->"

    result = run_orchestrated_translation(
        temp_dir=tmp_path,
        pages={"page0001.md": "retry me"},
        output_lang="zh",
        translate_fn=flaky_translate,
    )

    assert attempts == 3
    assert result["page0001.md"] == "<!-- START -->\n最终成功\n<!-- END -->"


def test_orchestrator_collects_failed_pages_and_continues(tmp_path: Path) -> None:
    attempts: dict[str, int] = {}

    def sometimes_fail(text: str, _: str) -> str:
        attempts[text] = attempts.get(text, 0) + 1
        if text == "always fail":
            raise RuntimeError("terminal page failure")
        return f"ok::{text}"

    result = run_orchestrated_translation(
        temp_dir=tmp_path,
        pages={
            "page0001.md": "always fail",
            "page0002.md": "succeeds",
        },
        output_lang="zh",
        translate_fn=sometimes_fail,
        max_retries=5,
    )

    assert attempts["always fail"] == 5
    assert attempts["succeeds"] == 1
    assert result == {"page0002.md": "ok::succeeds"}

    metrics = json.loads((tmp_path / "orchestration" / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["failed_pages"] == ["page0001.md"]
    assert metrics["failed_page_errors"]["page0001.md"] == "terminal page failure"
