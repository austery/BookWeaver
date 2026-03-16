from __future__ import annotations

from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dev_dependencies_include_ruff() -> None:
    pyproject_path = REPO_ROOT / "pyproject.toml"
    pyproject_data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    dev_dependencies = pyproject_data.get("dependency-groups", {}).get("dev", [])

    assert any(dependency.startswith("ruff") for dependency in dev_dependencies), (
        "Expected dependency-groups.dev to include ruff"
    )


def test_lint_workflow_exists_with_required_quality_gate_steps() -> None:
    workflow_path = REPO_ROOT / ".github" / "workflows" / "lint.yml"
    assert workflow_path.exists(), "Expected .github/workflows/lint.yml to exist"

    workflow_content = workflow_path.read_text(encoding="utf-8")
    required_snippets = [
        "name: lint-and-test",
        "ruff check",
        "ruff format --check",
        "uv run pytest -q",
        "needs: lint",
    ]

    for snippet in required_snippets:
        assert snippet in workflow_content, (
            f"Expected lint workflow to include: {snippet}"
        )
