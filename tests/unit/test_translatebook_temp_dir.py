from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "translatebook.sh"


def _resolve_temp_dir(input_file: str) -> str:
    command = f'source "{SCRIPT_PATH}" >/dev/null; resolve_temp_dir "{input_file}"'
    completed = subprocess.run(
        ["bash", "-lc", command],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def test_resolve_temp_dir_uses_basename_for_nested_input_path() -> None:
    assert _resolve_temp_dir("tmp/Psycho-Cybernetics.epub") == "Psycho-Cybernetics_temp"
