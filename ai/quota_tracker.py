from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# NOTE: QuotaTracker is not yet wired into the main pipeline. It exists as
# infrastructure for future rate-limiting and quota enforcement.


class QuotaTracker:
    def __init__(self, db_path: str) -> None:
        self.db_path = str(Path(db_path).expanduser())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS quota_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    date TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def record_usage(
        self, model: str, tier: str, token_count: int, date: str | None = None
    ) -> None:
        if token_count < 0:
            raise ValueError("token_count must be >= 0")
        usage_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO quota_usage (model, tier, date, token_count, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (model, tier, usage_date, token_count, created_at),
            )
            conn.commit()

    def get_daily_usage(self, model: str, date: str | None = None) -> int:
        usage_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(token_count), 0)
                FROM quota_usage
                WHERE model = ? AND date = ?
                """,
                (model, usage_date),
            ).fetchone()
        if row is None:
            return 0
        return int(row[0])
