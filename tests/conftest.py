from pathlib import Path
import tempfile

import pytest


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_chunk_en():
    return (
        "The rapid advancement of artificial intelligence has transformed "
        "multiple sectors of society."
    )
