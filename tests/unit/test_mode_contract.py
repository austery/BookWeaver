import pytest

from ai.mode_contract import DEFAULT_WORKFLOW_MODE, parse_workflow_mode


def test_parse_workflow_mode_accepts_fast_orchestrated_and_auto() -> None:
    assert parse_workflow_mode("fast") == "fast"
    assert parse_workflow_mode("orchestrated") == "orchestrated"
    assert parse_workflow_mode("auto") == "auto"
    assert parse_workflow_mode(None) == "fast"
    assert DEFAULT_WORKFLOW_MODE == "fast"


@pytest.mark.parametrize("value", ["unknown"])
def test_parse_workflow_mode_rejects_unknown_values(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid workflow mode"):
        parse_workflow_mode(value)


def test_parse_workflow_mode_rejects_empty_string() -> None:
    with pytest.raises(ValueError, match="Invalid workflow mode"):
        parse_workflow_mode("")
