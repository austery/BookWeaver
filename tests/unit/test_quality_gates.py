from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import shlex
import tomllib

from packaging.requirements import InvalidRequirement, Requirement


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_BLOCK_MARKERS = {"|", ">", "|-", ">-"}
INLINE_RUN_PATTERN = re.compile(r"^-\s+run:\s*(.+)$")
RUN_PATTERN = re.compile(r"^run:\s*(.+)$")


@dataclass
class WorkflowJob:
    needs: set[str] = field(default_factory=set)
    run_commands: list[str] = field(default_factory=list)


@dataclass
class WorkflowDefinition:
    name: str | None = None
    jobs: dict[str, WorkflowJob] = field(default_factory=dict)


def _strip_inline_comment(line: str) -> str:
    in_single_quote = False
    in_double_quote = False

    for index, char in enumerate(line):
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == "#" and not in_single_quote and not in_double_quote:
            if index == 0 or line[index - 1].isspace():
                return line[:index].rstrip()

    return line.rstrip()


def _parse_scalar(value: str) -> str:
    return value.strip().strip("'").strip('"')


def _parse_needs_value(value: str) -> set[str]:
    stripped = value.strip()
    if not stripped:
        return set()

    if stripped.startswith("[") and stripped.endswith("]"):
        items = [_parse_scalar(item) for item in stripped[1:-1].split(",")]
        return {item for item in items if item}

    return {_parse_scalar(stripped)}


def _append_run_command(job: WorkflowJob, value: str) -> None:
    parsed = _parse_scalar(value)
    if parsed:
        job.run_commands.append(parsed)


def _flush_run_block(job: WorkflowJob | None, run_block_lines: list[str]) -> None:
    if job is None:
        return

    for block_line in run_block_lines:
        _append_run_command(job, block_line)


def _extract_run_value(stripped_line: str) -> str | None:
    inline_match = INLINE_RUN_PATTERN.match(stripped_line)
    if inline_match:
        return inline_match.group(1)

    run_match = RUN_PATTERN.match(stripped_line)
    if run_match:
        return run_match.group(1)

    return None


def _parse_lint_workflow_definition(workflow_content: str) -> WorkflowDefinition:
    workflow = WorkflowDefinition()
    current_job_id: str | None = None
    in_steps = False
    collecting_needs_indent: int | None = None
    collecting_run_indent: int | None = None
    run_block_lines: list[str] = []

    for raw_line in workflow_content.splitlines():
        line_without_comment = _strip_inline_comment(raw_line)
        if not line_without_comment.strip():
            continue

        indent = len(line_without_comment) - len(line_without_comment.lstrip(" "))
        stripped = line_without_comment.strip()

        if collecting_run_indent is not None and indent > collecting_run_indent:
            run_block_lines.append(stripped)
            continue
        if collecting_run_indent is not None and indent <= collecting_run_indent:
            current_job = workflow.jobs[current_job_id] if current_job_id is not None else None
            _flush_run_block(current_job, run_block_lines)
            collecting_run_indent = None
            run_block_lines = []

        if collecting_needs_indent is not None and indent > collecting_needs_indent:
            if stripped.startswith("- ") and current_job_id is not None:
                workflow.jobs[current_job_id].needs.add(_parse_scalar(stripped[2:]))
            continue
        if collecting_needs_indent is not None and indent <= collecting_needs_indent:
            collecting_needs_indent = None

        if indent == 0 and stripped.startswith("name:"):
            workflow.name = _parse_scalar(stripped.partition(":")[2])
            continue

        if indent == 2 and stripped.endswith(":"):
            current_job_id = stripped[:-1]
            workflow.jobs[current_job_id] = WorkflowJob()
            in_steps = False
            continue

        if current_job_id is None:
            continue

        if indent == 4 and stripped.startswith("needs:"):
            needs_value = stripped.partition(":")[2]
            parsed_needs = _parse_needs_value(needs_value)
            if parsed_needs:
                workflow.jobs[current_job_id].needs.update(parsed_needs)
            else:
                collecting_needs_indent = indent
            continue

        if indent == 4 and stripped == "steps:":
            in_steps = True
            continue

        if indent <= 4:
            in_steps = False

        if not in_steps:
            continue

        run_value = _extract_run_value(stripped)
        if run_value is None:
            continue

        if run_value in RUN_BLOCK_MARKERS:
            collecting_run_indent = indent
        else:
            _append_run_command(workflow.jobs[current_job_id], run_value)

    if collecting_run_indent is not None and current_job_id is not None:
        _flush_run_block(workflow.jobs[current_job_id], run_block_lines)

    return workflow


def _dependency_name(raw_dependency: object) -> str | None:
    if not isinstance(raw_dependency, str):
        return None

    try:
        return Requirement(raw_dependency).name
    except InvalidRequirement:
        return None


def _command_contains_tokens(command: str, expected_tokens: tuple[str, ...]) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False

    if len(tokens) < len(expected_tokens):
        return False

    for index in range(len(tokens) - len(expected_tokens) + 1):
        if tuple(tokens[index : index + len(expected_tokens)]) == expected_tokens:
            return True

    return False


def test_dev_dependencies_include_ruff() -> None:
    pyproject_path = REPO_ROOT / "pyproject.toml"
    pyproject_data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    dev_dependencies = pyproject_data.get("dependency-groups", {}).get("dev", [])

    assert any(_dependency_name(dependency) == "ruff" for dependency in dev_dependencies), (
        "Expected dependency-groups.dev to include ruff"
    )


def test_lint_workflow_exists_with_required_quality_gate_steps() -> None:
    workflow_path = REPO_ROOT / ".github" / "workflows" / "lint.yml"
    assert workflow_path.exists(), "Expected .github/workflows/lint.yml to exist"

    workflow = _parse_lint_workflow_definition(workflow_path.read_text(encoding="utf-8"))
    assert workflow.name == "lint-and-test", "Expected workflow name to be lint-and-test"

    lint_job_id = next(
        (
            job_id
            for job_id, job in workflow.jobs.items()
            if any(
                _command_contains_tokens(command, ("ruff", "check")) for command in job.run_commands
            )
            and any(
                _command_contains_tokens(command, ("ruff", "format", "--check"))
                for command in job.run_commands
            )
        ),
        None,
    )
    assert lint_job_id is not None, (
        "Expected a lint job with run steps for 'ruff check' and 'ruff format --check'"
    )

    has_downstream_pytest_job = any(
        lint_job_id in job.needs
        and any(
            _command_contains_tokens(command, ("uv", "run", "pytest", "-q"))
            for command in job.run_commands
        )
        for job in workflow.jobs.values()
    )
    assert has_downstream_pytest_job, (
        f"Expected at least one job that needs '{lint_job_id}' and runs 'uv run pytest -q'"
    )
