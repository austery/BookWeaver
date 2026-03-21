from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_step3_module():
    project_root = Path(__file__).resolve().parents[2]
    file_path = project_root / "03_translate_md.py"
    spec = importlib.util.spec_from_file_location("step3_module_integration", file_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load 03_translate_md.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fast_and_orchestrated_emit_output_page_contract(tmp_path: Path) -> None:
    module = _load_step3_module()

    fast_dir = tmp_path / "fast"
    orch_dir = tmp_path / "orchestrated"
    fast_dir.mkdir(parents=True, exist_ok=True)
    orch_dir.mkdir(parents=True, exist_ok=True)

    (fast_dir / "page0001.md").write_text("Hello fast", encoding="utf-8")
    (orch_dir / "page0001.md").write_text("Hello orch", encoding="utf-8")

    module.translate_with_gemini_cli = lambda *args, **kwargs: "FAST:translated"
    module.select_model_with_fallback = lambda *args, **kwargs: "gemini-2.5-flash"
    module.time.sleep = lambda *_: None
    module.run_orchestrated_translation = lambda *, temp_dir, pages, output_lang: {
        name: f"ORCH:{content}" for name, content in pages.items()
    }

    runtime_config = {"default_model": "gemini-2.5-flash"}
    module.translate_markdown_files(
        str(fast_dir),
        "zh",
        runtime_config=runtime_config,
        workflow_mode="fast",
    )
    module.translate_markdown_files(
        str(orch_dir),
        "zh",
        runtime_config=runtime_config,
        workflow_mode="orchestrated",
    )

    fast_out = fast_dir / "output_page0001.md"
    orch_out = orch_dir / "output_page0001.md"
    assert fast_out.exists()
    assert orch_out.exists()
    assert fast_out.read_text(encoding="utf-8")
    assert orch_out.read_text(encoding="utf-8")
