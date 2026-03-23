from __future__ import annotations

from pathlib import Path

import pytest

from ai.quota_tracker import QuotaTracker


def test_quota_tracker_initializes_db(temp_dir: Path):
    db_path = temp_dir / "quota.db"
    tracker = QuotaTracker(str(db_path))
    assert Path(tracker.db_path).exists()


def test_quota_tracker_records_and_reads_usage(temp_dir: Path):
    db_path = temp_dir / "quota.db"
    tracker = QuotaTracker(str(db_path))
    tracker.record_usage(model="gemini-2.5-flash", tier="flash", token_count=500)
    tracker.record_usage(model="gemini-2.5-flash", tier="flash", token_count=300)
    total = tracker.get_daily_usage(model="gemini-2.5-flash")
    assert total == 800


def test_record_usage_negative_raises(temp_dir: Path) -> None:
    db_path = temp_dir / "quota.db"
    tracker = QuotaTracker(str(db_path))
    with pytest.raises(ValueError, match="token_count must be >= 0"):
        tracker.record_usage(model="gemini-2.5-flash", tier="flash", token_count=-1)


def test_get_daily_usage_no_records_returns_zero(temp_dir: Path) -> None:
    db_path = temp_dir / "quota.db"
    tracker = QuotaTracker(str(db_path))
    assert tracker.get_daily_usage(model="gemini-2.5-flash") == 0


def test_get_daily_usage_cross_date_isolation(temp_dir: Path) -> None:
    """Yesterday's usage must not count toward today's quota."""
    db_path = temp_dir / "quota.db"
    tracker = QuotaTracker(str(db_path))
    tracker.record_usage(
        model="gemini-2.5-flash", tier="flash", token_count=1000, date="2026-01-01"
    )
    result = tracker.get_daily_usage(model="gemini-2.5-flash", date="2026-01-02")
    assert result == 0
