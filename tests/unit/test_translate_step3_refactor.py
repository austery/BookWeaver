from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


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


def test_step3_create_translation_prompt_from_external_template(tmp_path):
    module = _load_step3_module()
    template_path = tmp_path / "prompt.txt"
    template_path.write_text(
        "Translate to {TARGET_LANGUAGE}\n{CUSTOM_INSTRUCTIONS_BLOCK}\nBody:",
        encoding="utf-8",
    )
    config = {
        "prompt_profile": "default",
        "prompt_templates": {"default": str(template_path)},
    }
    prompt = module.create_translation_prompt(
        "zh",
        "extra-rule",
        runtime_config=config,
    )
    assert "ADDITIONAL INSTRUCTIONS" in prompt


def test_step3_resolve_model_name_supports_alias():
    module = _load_step3_module()
    config = {"model_aliases": {"pro": "gemini-2.5-pro"}}
    assert module.resolve_model_name("pro", config) == "gemini-2.5-pro"


def test_step3_fallback_chain_selects_first_available():
    module = _load_step3_module()

    class FakeProbe:
        def __init__(self) -> None:
            self.last_probe_errors = {"gemini-2.5-pro": "not available"}

        def probe(self, candidates: list[str]) -> dict[str, bool]:
            assert candidates == ["gemini-2.5-pro", "gemini-2.5-flash"]
            return {"gemini-2.5-pro": False, "gemini-2.5-flash": True}

    config = {
        "model_aliases": {
            "pro": "gemini-2.5-pro",
            "flash": "gemini-2.5-flash",
        },
        "fallback_chain": ["flash"],
        "model_probe": {"enabled": True},
    }

    selected_model = module.select_model_with_fallback("pro", config, probe=FakeProbe())
    assert selected_model == "gemini-2.5-flash"


def test_step3_prompt_without_placeholder_still_appends_custom_block(tmp_path):
    module = _load_step3_module()
    template_path = tmp_path / "prompt.txt"
    template_path.write_text("Translate to {TARGET_LANGUAGE}\nBody:", encoding="utf-8")
    config = {
        "prompt_profile": "default",
        "prompt_templates": {"default": str(template_path)},
    }

    prompt = module.create_translation_prompt(
        "zh",
        custom_prompt="be concise",
        runtime_config=config,
    )
    assert "ADDITIONAL INSTRUCTIONS" in prompt


def test_step3_parse_arguments_supports_skip_probe_preview(monkeypatch):
    module = _load_step3_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "03_translate_md.py",
            "--temp-dir",
            "/tmp/demo",
            "--preview-model-selection",
            "--skip-probe",
        ],
    )
    args = module.parse_arguments()
    assert args.preview_model_selection is True
    assert args.skip_probe is True


def test_step3_parse_arguments_supports_no_resume(monkeypatch):
    module = _load_step3_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "03_translate_md.py",
            "--temp-dir",
            "/tmp/demo",
            "--no-resume",
        ],
    )
    args = module.parse_arguments()
    assert args.no_resume is True


def test_step3_translate_markdown_files_can_disable_resume(monkeypatch, temp_dir):
    module = _load_step3_module()

    page_file = temp_dir / "page0001.md"
    page_file.write_text("Hello world", encoding="utf-8")
    output_file = temp_dir / "output_page0001.md"
    output_file.write_text("old translation", encoding="utf-8")

    monkeypatch.setattr(
        module, "select_model_with_fallback", lambda *args, **kwargs: "gemini-2.5-flash"
    )
    monkeypatch.setattr(
        module, "translate_with_gemini_cli", lambda *args, **kwargs: "new translation"
    )
    monkeypatch.setattr(module.time, "sleep", lambda *_: None)

    module.translate_markdown_files(
        str(temp_dir),
        "zh",
        runtime_config={"default_model": "gemini-2.5-flash"},
        resume=False,
    )

    assert output_file.read_text(encoding="utf-8") == "new translation"
    progress_log = temp_dir / "translation_progress.log"
    assert progress_log.exists()
    assert "page0001.md" in progress_log.read_text(encoding="utf-8")


def test_load_runtime_config_invalid_json_raises_with_message(tmp_path: Path, monkeypatch) -> None:
    module = _load_step3_module()

    # Create the user config path that load_runtime_config() looks for:
    # Path.home() / ".config" / "translatebook" / "config.json"
    config_dir = tmp_path / ".config" / "translatebook"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text("{not valid json", encoding="utf-8")

    # Patch Path.home so it returns tmp_path instead of the real home directory.
    # Path.home is a classmethod, so we patch it as a staticmethod returning tmp_path.
    import pathlib

    monkeypatch.setattr(pathlib.Path, "home", staticmethod(lambda: tmp_path))

    with pytest.raises(json.JSONDecodeError):
        module.load_runtime_config()


def test_load_runtime_config_permission_error(tmp_path: Path, monkeypatch) -> None:
    """PermissionError on user config propagates with path info."""
    module = _load_step3_module()
    config_dir = tmp_path / ".config" / "translatebook"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.json"
    config_path.write_text('{"default_model": "flash"}', encoding="utf-8")
    config_path.chmod(0o000)  # no-read

    import pathlib

    monkeypatch.setattr(pathlib.Path, "home", staticmethod(lambda: tmp_path))

    try:
        with pytest.raises(PermissionError):
            module.load_runtime_config()
    finally:
        config_path.chmod(0o644)  # restore so tmp_path cleanup works
