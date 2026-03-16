from __future__ import annotations

import importlib.util
import sys
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


def test_step3_load_runtime_config_has_default_model():
    module = _load_step3_module()
    config = module.load_runtime_config()
    assert isinstance(config, dict)
    assert config.get("default_model"), "Expected default_model in runtime config"

