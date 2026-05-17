import sqlite3
from datetime import UTC, datetime, timedelta

from src.db.repository import insert_event
from src.engine.compaction import compaction_status, run_compaction
from src.models.event import EventEntry, EventSeverity, EventType


def _old_event(days_ago: int = 35) -> EventEntry:
    return EventEntry(
        source="old-svc",
        event_type=EventType.info,
        severity=EventSeverity.info,
        message="old event",
        timestamp=datetime.now(UTC) - timedelta(days=days_ago),
    )


def _recent_event() -> EventEntry:
    return EventEntry(
        source="recent-svc",
        event_type=EventType.info,
        severity=EventSeverity.info,
        message="recent event",
        timestamp=datetime.now(UTC),
    )


def test_compaction_marks_old_records(db_conn: sqlite3.Connection) -> None:
    insert_event(db_conn, _old_event(35))
    insert_event(db_conn, _recent_event())
    results = run_compaction(db_conn, compaction_days=30)
    assert results["events"] == 1
    compacted = db_conn.execute("SELECT COUNT(*) FROM events WHERE compacted=1").fetchone()[0]
    assert compacted == 1
    not_compacted = db_conn.execute("SELECT COUNT(*) FROM events WHERE compacted=0").fetchone()[0]
    assert not_compacted == 1


def test_compaction_never_deletes(db_conn: sqlite3.Connection) -> None:
    insert_event(db_conn, _old_event(35))
    run_compaction(db_conn, compaction_days=30)
    total = db_conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert total == 1


def test_compaction_no_old_records(db_conn: sqlite3.Connection) -> None:
    insert_event(db_conn, _recent_event())
    results = run_compaction(db_conn, compaction_days=30)
    assert results["events"] == 0


def test_compaction_idempotent(db_conn: sqlite3.Connection) -> None:
    insert_event(db_conn, _old_event(35))
    run_compaction(db_conn, compaction_days=30)
    results2 = run_compaction(db_conn, compaction_days=30)
    assert results2["events"] == 0


def test_compaction_status_returns_history(db_conn: sqlite3.Connection) -> None:
    insert_event(db_conn, _old_event(35))
    run_compaction(db_conn, compaction_days=30)
    history = compaction_status(db_conn)
    assert len(history) >= 1
    assert "table_name" in history[0]
    assert "records_marked" in history[0]
