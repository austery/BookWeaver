from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


def _load_step3_module():
    project_root = Path(__file__).resolve().parents[2]
    file_path = project_root / "03_translate_md.py"
    spec = importlib.util.spec_from_file_location("step3_module", file_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load 03_translate_md.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_step3_exposes_gemini_cli_check():
    module = _load_step3_module()
    assert hasattr(module, "check_gemini_cli"), "Expected check_gemini_cli function"


def test_step3_parse_arguments_accepts_model(monkeypatch):
    module = _load_step3_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "03_translate_md.py",
            "--temp-dir",
            "/tmp/demo",
            "--model",
            "gemini-2.5-pro",
        ],
    )
    args = module.parse_arguments()
    assert args.model == "gemini-2.5-pro"


def test_step3_parse_arguments_accepts_non_hardcoded_model(monkeypatch):
    module = _load_step3_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "03_translate_md.py",
            "--temp-dir",
            "/tmp/demo",
            "--model",
            "gemini-3-pro-preview",
        ],
    )
    args = module.parse_arguments()
    assert args.model == "gemini-3-pro-preview"


def test_step3_load_runtime_config_has_default_model():
    module = _load_step3_module()
    config = module.load_runtime_config()
    assert isinstance(config, dict)
    assert config.get("default_model"), "Expected default_model in runtime config"


def test_step3_resolve_model_name_supports_alias():
    module = _load_step3_module()
    config = {"model_aliases": {"pro": "gemini-2.5-pro"}}
    assert module.resolve_model_name("pro", config) == "gemini-2.5-pro"
    assert module.resolve_model_name("gemini-3-pro-preview", config) == "gemini-3-pro-preview"


def test_step3_create_translation_prompt_from_external_template():
    module = _load_step3_module()
    with tempfile.TemporaryDirectory() as tmpdir:
        tpl = Path(tmpdir) / "p.txt"
        tpl.write_text(
            "Target={TARGET_LANGUAGE}\\n{CUSTOM_INSTRUCTIONS_BLOCK}\\nBody:",
            encoding="utf-8",
        )
        config = {
            "prompt_profile": "default",
            "prompt_templates": {"default": str(tpl)},
        }
        prompt = module.create_translation_prompt("zh", "extra-rule", runtime_config=config)
        assert "Target=Chinese" in prompt
        assert "ADDITIONAL INSTRUCTIONS" in prompt
        assert "extra-rule" in prompt
