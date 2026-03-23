from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_chunk_en() -> str:
    return (
        "The rapid advancement of artificial intelligence has transformed "
        "multiple sectors of society."
    )
