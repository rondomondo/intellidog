import sqlite3
from datetime import UTC, datetime

from src.db.repository import insert_event
from src.engine.llm_analyser import MockLLMAnalyser
from src.models.event import EventEntry, EventSeverity, EventType


def _event(source: str = "svc", severity: str = "info", duration_ms: int = 100) -> EventEntry:
    return EventEntry(
        source=source,
        event_type=EventType.error,
        severity=EventSeverity(severity),
        message="test event",
        payload={"duration_ms": duration_ms},
        timestamp=datetime.now(UTC),
    )


def test_mock_is_always_enabled() -> None:
    m = MockLLMAnalyser()
    m.connect()
    assert m.is_enabled()


def test_mock_no_events_returns_empty(db_conn: sqlite3.Connection) -> None:
    m = MockLLMAnalyser()
    m.connect()
    assert m.analyse(db_conn) == []


def test_mock_detects_high_error_rate(db_conn: sqlite3.Connection) -> None:
    for _ in range(8):
        insert_event(db_conn, _event(severity="critical"))
    for _ in range(2):
        insert_event(db_conn, _event(severity="info"))
    m = MockLLMAnalyser()
    alerts = m.analyse(db_conn)
    titles = [a.rule_name for a in alerts]
    assert any("Error Rate" in t for t in titles)


def test_mock_detects_latency_spike(db_conn: sqlite3.Connection) -> None:
    for _ in range(3):
        insert_event(db_conn, _event(duration_ms=8000))
    m = MockLLMAnalyser()
    alerts = m.analyse(db_conn)
    titles = [a.rule_name for a in alerts]
    assert any("Latency" in t for t in titles)


def test_mock_detects_source_burst(db_conn: sqlite3.Connection) -> None:
    for _ in range(7):
        insert_event(db_conn, _event(source="noisy-service", severity="info", duration_ms=10))
    m = MockLLMAnalyser()
    alerts = m.analyse(db_conn)
    titles = [a.rule_name for a in alerts]
    assert any("Burst" in t for t in titles)


def test_mock_alerts_have_llm_source(db_conn: sqlite3.Connection) -> None:
    for _ in range(8):
        insert_event(db_conn, _event(severity="critical"))
    m = MockLLMAnalyser()
    alerts = m.analyse(db_conn)
    assert all(a.source == "llm" for a in alerts)


def test_mock_alerts_have_mock_flag(db_conn: sqlite3.Connection) -> None:
    for _ in range(8):
        insert_event(db_conn, _event(severity="critical"))
    m = MockLLMAnalyser()
    alerts = m.analyse(db_conn)
    assert all(a.details.get("mock") is True for a in alerts)


def test_mock_alerts_persisted_to_db(db_conn: sqlite3.Connection) -> None:
    for _ in range(8):
        insert_event(db_conn, _event(severity="critical"))
    m = MockLLMAnalyser()
    alerts = m.analyse(db_conn)
    count = db_conn.execute("SELECT COUNT(*) FROM alerts WHERE source='llm'").fetchone()[0]
    assert count == len(alerts)
