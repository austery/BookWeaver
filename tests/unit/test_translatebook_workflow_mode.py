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
        f'source "{SCRIPT_PATH}" >/dev/null; resolve_workflow_for_input "{input_file}" "{override}"'
    )
    return subprocess.run(
        ["bash", "-lc", command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_script_shell(command: str) -> subprocess.CompletedProcess[str]:
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


def test_parse_args_rejects_invalid_workflow_override(tmp_path: Path) -> None:
    input_file = tmp_path / "book.pdf"
    input_file.write_text("demo", encoding="utf-8")
    command = f'source "{SCRIPT_PATH}" >/dev/null; parse_args --workflow invalid "{input_file}"'
    completed = _run_script_shell(command)

    assert completed.returncode == 2
    combined_output = f"{completed.stdout}\n{completed.stderr}"
    assert "Invalid workflow mode" in combined_output


def test_show_config_displays_resolved_workflow_state() -> None:
    command = (
        f'source "{SCRIPT_PATH}" >/dev/null; '
        'INPUT_FILE="book.pdf"; '
        'WORKFLOW_OVERRIDE=""; '
        'RESOLVED_WORKFLOW="$(resolve_workflow_for_input "$INPUT_FILE" "$WORKFLOW_OVERRIDE")"; '
        "show_config"
    )
    completed = _run_script_shell(command)

    assert completed.returncode == 0, completed.stderr
    assert "Workflow override: auto" in completed.stdout
    assert "Resolved workflow: markdown" in completed.stdout
