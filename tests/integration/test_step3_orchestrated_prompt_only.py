from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_step3_module():
    project_root = Path(__file__).resolve().parents[2]
    file_path = project_root / "03_translate_md.py"
    spec = importlib.util.spec_from_file_location(
        "step3_module_orchestrated_prompt_only", file_path
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load 03_translate_md.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_orchestrated_prompt_only_writes_artifacts_without_output_pages(tmp_path: Path) -> None:
    module = _load_step3_module()
    temp_dir = tmp_path / "orchestrated_prompt_only"
    temp_dir.mkdir(parents=True, exist_ok=True)
    (temp_dir / "page0001.md").write_text("Source paragraph.", encoding="utf-8")

    def fake_orchestrated(
        *,
        temp_dir: Path,
        pages: dict[str, str],
        output_lang: str,
        model: str,
        custom_prompt: str | None,
        max_retries: int,
        runtime_config: dict[str, object] | None,
        phase: str,
    ) -> dict[str, str]:
        assert phase == "prompt-only"
        assert pages == {"page0001.md": "Source paragraph."}
        assert output_lang == "zh"

        orchestration_dir = temp_dir / "orchestration"
        orchestration_dir.mkdir(parents=True, exist_ok=True)
        (orchestration_dir / "01-analysis.md").write_text("analysis", encoding="utf-8")
        (orchestration_dir / "02-prompt.md").write_text("prompt", encoding="utf-8")
        (orchestration_dir / "metrics.json").write_text(
            json.dumps({"mode": "orchestrated", "phase": "prompt-only", "pages": 1}),
            encoding="utf-8",
        )
        return {}

    module.run_orchestrated_translation = fake_orchestrated

    module.translate_markdown_files(
        str(temp_dir),
        "zh",
        runtime_config={"default_model": "gemini-2.5-flash"},
        workflow_mode="orchestrated",
        orchestrated_phase="prompt-only",
    )

    orchestration_dir = temp_dir / "orchestration"
    assert (orchestration_dir / "01-analysis.md").exists()
    assert (orchestration_dir / "02-prompt.md").exists()
    assert (orchestration_dir / "metrics.json").exists()
    assert not list(temp_dir.glob("output_page*.md"))
