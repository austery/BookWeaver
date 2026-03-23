# tests/unit/test_pipeline_utils.py
from __future__ import annotations

import pytest
from pathlib import Path


def test_load_pipeline_config_returns_dict(tmp_path: Path) -> None:
    config_file = tmp_path / "config.txt"
    config_file.write_text("input_lang=en\noutput_lang=zh\nmodel=flash\n", encoding="utf-8")
    from pipeline_utils import load_pipeline_config

    result = load_pipeline_config(str(tmp_path))
    assert result["input_lang"] == "en"
    assert result["output_lang"] == "zh"
    assert result["model"] == "flash"


def test_load_pipeline_config_file_not_found(tmp_path: Path) -> None:
    from pipeline_utils import load_pipeline_config

    with pytest.raises(FileNotFoundError) as exc_info:
        load_pipeline_config(str(tmp_path))
    assert "01_convert_to_htmlz.py" in str(exc_info.value)


def test_load_pipeline_config_unicode_error(tmp_path: Path) -> None:
    config_file = tmp_path / "config.txt"
    config_file.write_bytes(b"key=\xff\xfe\n")  # invalid UTF-8
    from pipeline_utils import load_pipeline_config

    with pytest.raises(UnicodeDecodeError):
        load_pipeline_config(str(tmp_path))


def test_get_language_name_known_codes() -> None:
    from pipeline_utils import get_language_name

    assert get_language_name("zh") == "Chinese"
    assert get_language_name("en") == "English"
    assert get_language_name("ja") == "Japanese"
    assert get_language_name("fr") == "French"
    assert get_language_name("ZH") == "Chinese"  # case-insensitive


def test_get_language_name_unknown_code() -> None:
    from pipeline_utils import get_language_name

    assert get_language_name("xx") == "xx"
    assert get_language_name("UNKNOWN") == "UNKNOWN"
