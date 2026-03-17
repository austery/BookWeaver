from typing import Literal

WorkflowMode = Literal["fast", "orchestrated", "auto"]
DEFAULT_WORKFLOW_MODE: WorkflowMode = "fast"


def parse_workflow_mode(raw: str | None) -> WorkflowMode:
    normalized = (raw or DEFAULT_WORKFLOW_MODE).strip().lower()
    if normalized in {"fast", "orchestrated", "auto"}:
        return normalized
    raise ValueError(f"Invalid workflow mode: {raw}")
