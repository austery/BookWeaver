from ai.mode_contract import DEFAULT_WORKFLOW_MODE, parse_workflow_mode


def test_parse_workflow_mode_accepts_fast_and_orchestrated() -> None:
    assert parse_workflow_mode("fast") == "fast"
    assert parse_workflow_mode("orchestrated") == "orchestrated"
    assert DEFAULT_WORKFLOW_MODE == "fast"


def test_parse_workflow_mode_rejects_unknown_value() -> None:
    try:
        parse_workflow_mode("unknown")
    except ValueError as exc:
        assert "workflow mode" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError for invalid mode")
