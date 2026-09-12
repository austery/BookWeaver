"""The converged runtime rejects configuration drift before execution."""

from pathlib import Path

import pytest

from ai.runtime_config import validate_config


def test_legacy_model_mapping_is_rejected() -> None:
    with pytest.raises(ValueError, match="model_aliases"):
        validate_config({"model_aliases": {"flash": "obsolete"}})


def test_unknown_nested_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="typo"):
        validate_config({"sanity_probe": {"typo": True}})


def test_explicit_zero_batch_limit_is_rejected() -> None:
    with pytest.raises(ValueError):
        validate_config({"epub_resilience": {"standard_epub_max_batch_chars": 0}})


@pytest.mark.parametrize("checkout", [True, False])
def test_config_locations_and_user_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, checkout: bool
) -> None:
    from ai import runtime_config

    root, home = tmp_path / "layout", tmp_path / "user"
    (root / "ai").mkdir(parents=True)
    (root / "config").mkdir()
    (home / ".config/bookweaver").mkdir(parents=True)
    monkeypatch.setattr(runtime_config, "__file__", str(root / "ai/runtime_config.py"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    if checkout:
        (root / "pyproject.toml").write_text('[project]\nname = "bookweaver"\n')
        (root / "config/config.json").write_text(
            '{"sanity_probe": {"enabled": false, "heartbeat_chars": 20}}'
        )
    else:
        (root / "config/config.json").write_text('{"removed_key": true}')
        (root / "pyproject.toml").write_text('[project]\nname = "unrelated"\n')
    user = home / ".config/bookweaver/config.json"
    user.write_text('{"sanity_probe": {"enabled": true}}')
    before = user.read_bytes()
    config = runtime_config.load_runtime_config()
    assert config == {
        "sanity_probe": {"enabled": True, **({"heartbeat_chars": 20} if checkout else {})}
    }
    assert user.read_bytes() == before


@pytest.mark.parametrize(
    "contents", ['{"unknown": true}', '{"sanity_probe": {"heartbeat_chars": 0}}', "{broken"]
)
def test_user_config_errors_do_not_rewrite_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contents: str
) -> None:
    from ai.runtime_config import load_runtime_config

    config = tmp_path / ".config/bookweaver/config.json"
    config.parent.mkdir(parents=True)
    config.write_text(contents)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with pytest.raises(ValueError, match="Invalid runtime configuration"):
        load_runtime_config()
    assert config.read_text() == contents


def test_legacy_config_is_rejected_without_rewriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai.runtime_config import load_runtime_config

    legacy = tmp_path / ".config/translatebook/config.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("{}")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with pytest.raises(ValueError, match="Legacy"):
        load_runtime_config()
    assert legacy.read_text() == "{}"
