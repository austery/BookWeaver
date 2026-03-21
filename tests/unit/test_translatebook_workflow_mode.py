from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "translatebook.sh"


def _resolve_workflow_for_input(
    input_file: str,
    workflow_override: str | None = None,
) -> subprocess.CompletedProcess[str]:
    override = workflow_override or ""
    command = (
        f'source "{SCRIPT_PATH}" >/dev/null; '
        f'resolve_workflow_for_input "{input_file}" "{override}"'
    )
    return subprocess.run(
        ["bash", "-lc", command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_workflow_defaults_to_epub_for_epub_input() -> None:
    completed = _resolve_workflow_for_input("book.epub")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "epub"


def test_workflow_defaults_to_markdown_for_pdf_input() -> None:
    completed = _resolve_workflow_for_input("book.pdf")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "markdown"


def test_workflow_respects_markdown_override_for_epub_input() -> None:
    completed = _resolve_workflow_for_input("book.epub", "markdown")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "markdown"
