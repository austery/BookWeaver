from __future__ import annotations

from pathlib import Path

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
