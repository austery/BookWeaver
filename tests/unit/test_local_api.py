"""Local API contract at the HTTP boundary (SPEC-026 Phase 2)."""

from __future__ import annotations

import json
import sys

import pytest
from fastapi.testclient import TestClient

import ai.cli as entry_module
from ai import local_api


@pytest.fixture
def client() -> TestClient:
    return TestClient(local_api.create_app())


def test_rows_endpoint_matches_the_cli_listing(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    response = client.get("/rows")
    assert response.status_code == 200
    entry_module.main(["rows", "--json"])
    assert response.json() == json.loads(capsys.readouterr().out)
    assert response.json()[0]["name"] == "agy-flash-low"


def test_rows_schema_lists_choices_as_enums(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()["components"]["schemas"]["Row"]["properties"]
    assert schema["status"]["enum"] == ["default", "manual", "experiment"]
    assert "antigravity" in schema["runtime"]["enum"]


def test_docs_page_is_served(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200


def test_serve_binds_to_loopback_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, *, host, port: calls.append((host, port)))
    entry_module.main(["serve", "--port", "8800"])
    assert calls == [("127.0.0.1", 8800)]


def test_serve_rejects_an_invalid_port(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        entry_module.main(["serve", "--port", "0"])
    assert "between 1 and 65535" in capsys.readouterr().err


def test_serve_without_the_api_extra_names_the_install_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import uvicorn

    import ai

    def never_serve(*args: object, **kwargs: object) -> None:
        raise AssertionError("serve must not start without the api extra")

    monkeypatch.setattr(uvicorn, "run", never_serve)
    # Force a fresh import of ai.local_api with fastapi unavailable.
    monkeypatch.setitem(sys.modules, "fastapi", None)
    monkeypatch.delitem(sys.modules, "ai.local_api")
    monkeypatch.delattr(ai, "local_api")
    with pytest.raises(SystemExit):
        entry_module.main(["serve"])
    error = capsys.readouterr().err
    assert "fastapi" in error and "uv sync --extra api" in error
