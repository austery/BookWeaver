"""The converged runtime rejects configuration drift before execution."""

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
