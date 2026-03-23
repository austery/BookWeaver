from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


def _load_step3_module() -> types.ModuleType:
    project_root = Path(__file__).resolve().parents[2]
    file_path = project_root / "03_translate_md.py"
    spec = importlib.util.spec_from_file_location("step3_module", file_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load 03_translate_md.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_step3_exposes_gemini_cli_check() -> None:
    module = _load_step3_module()
    assert hasattr(module, "check_gemini_cli"), "Expected check_gemini_cli function"


def test_step3_parse_arguments_accepts_model(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_step3_parse_arguments_accepts_non_hardcoded_model(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_step3_load_runtime_config_has_default_model() -> None:
    module = _load_step3_module()
    config = module.load_runtime_config()
    assert isinstance(config, dict)
    assert config.get("default_model"), "Expected default_model in runtime config"


def test_step3_create_translation_prompt_from_external_template(tmp_path: Path) -> None:
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


def test_step3_resolve_model_name_supports_alias() -> None:
    module = _load_step3_module()
    config = {"model_aliases": {"pro": "gemini-2.5-pro"}}
    assert module.resolve_model_name("pro", config) == "gemini-2.5-pro"


def test_step3_fallback_chain_selects_first_available() -> None:
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


def test_step3_prompt_without_placeholder_still_appends_custom_block(tmp_path: Path) -> None:
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


def test_step3_parse_arguments_supports_skip_probe_preview(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_step3_parse_arguments_supports_no_resume(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_step3_translate_markdown_files_can_disable_resume(
    monkeypatch: pytest.MonkeyPatch, temp_dir: Path
) -> None:
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


def test_load_runtime_config_invalid_json_raises_with_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


def test_translate_files_resume_skips_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """resume=True must skip files that already have output_*.md."""
    module = _load_step3_module()

    # Create input and pre-existing output files
    input_file = tmp_path / "page0001.md"
    input_file.write_text("Some content", encoding="utf-8")
    output_file = tmp_path / "output_page0001.md"
    output_file.write_text("Already translated", encoding="utf-8")

    translate_calls: list[str] = []

    def fake_translate_with_gemini_cli(
        text: str, output_lang: str, model: str, custom_prompt: str | None = None, **kwargs: object
    ) -> str:
        translate_calls.append(text)
        return "translated"

    monkeypatch.setattr(module, "translate_with_gemini_cli", fake_translate_with_gemini_cli)

    module.translate_markdown_files(
        temp_dir=str(tmp_path),
        output_lang="zh",
        runtime_config={
            "default_model": "gemini-2.5-flash",
            "prompt_profile": "default",
            "prompt_templates": {"default": "config/prompts/default_prompt.txt"},
            "model_aliases": {},
            "fallback_chain": [],
            "model_probe": {"enabled": False},
        },
        resume=True,
    )
    assert translate_calls == [], "translation should NOT be attempted for existing output file"


def test_deep_merge_dict_nested_merge() -> None:
    """Nested keys should be merged, not replaced wholesale."""
    module = _load_step3_module()
    base = {"model_thresholds": {"small": {"max_chars": 5000, "model": "flash"}}}
    override = {"model_thresholds": {"small": {"model": "pro"}}}
    result = module._deep_merge_dict(base, override)
    assert result["model_thresholds"]["small"]["max_chars"] == 5000
    assert result["model_thresholds"]["small"]["model"] == "pro"


def test_resolve_model_alias_cycle_detection() -> None:
    """Alias cycles must raise ValueError with helpful message."""
    module = _load_step3_module()
    cyclic_config = {"model_aliases": {"pro": "flash", "flash": "pro"}}
    with pytest.raises(ValueError, match="cycle detected"):
        module.resolve_model_name("pro", runtime_config=cyclic_config)


def test_load_runtime_config_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
