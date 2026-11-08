"""Local HTTP API over the application path (SPEC-026); its generated /docs page is the UI.

Bound to 127.0.0.1 only. It reads the same named rows as the CLI and keeps no state of
its own. Requires the optional ``api`` extra (FastAPI and uvicorn), imported at module load so a
missing one is reported by the CLI before anything starts.
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from ai import orchestration

HOST = "127.0.0.1"


def create_app() -> FastAPI:
    """Build the API; separate from ``serve`` so tests can call it without a socket."""
    app = FastAPI(
        title="BookWeaver local API",
        description=(
            "Lists the enabled rows, the same as `bookweaver rows`. "
            "Starting runs arrives in SPEC-026 Phase 3."
        ),
        version="0.1.0",
    )

    @app.get(
        "/rows",
        response_model=list[orchestration.Row],
        summary="List enabled rows",
        description=(
            "Every selection a run may use, the default row first. Metered rows are paid "
            "and need per-run consent."
        ),
    )
    def list_rows() -> list[orchestration.Row]:
        return list(orchestration.enabled_rows())

    return app


def serve(port: int) -> None:
    """Run the API in the foreground until interrupted; never binds beyond this Mac."""
    uvicorn.run(create_app(), host=HOST, port=port)
