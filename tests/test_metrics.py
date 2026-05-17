from datetime import UTC, datetime

from fastapi.testclient import TestClient

from src.db.repository import insert_event
from src.models.event import EventEntry, EventSeverity, EventType


def _event(severity: str = "info", duration_ms: int = 100) -> EventEntry:
    return EventEntry(
        source="metrics-test",
        event_type=EventType.metric,
        severity=EventSeverity(severity),
        message="metrics test event",
        payload={"duration_ms": duration_ms},
        timestamp=datetime.now(UTC),
    )


def test_metrics_summary_empty(app_client: TestClient) -> None:
    r = app_client.get("/metrics/summary")
    assert r.status_code == 200
    data = r.json()
    assert "rate" in data
    assert "severity_breakdown" in data
    assert "latency" in data
    assert data["rate"]["total"] == 0


def test_metrics_summary_with_events(app_client: TestClient, db_conn) -> None:
    for _ in range(5):
        insert_event(db_conn, _event("high", 1000))
    for _ in range(3):
        insert_event(db_conn, _event("info", 50))
    app_client.app.state.db_conn = db_conn
    r = app_client.get("/metrics/summary", params={"window": 300})
    data = r.json()
    assert data["rate"]["total"] == 8
    assert data["rate"]["error_count"] == 5


def test_metrics_summary_window_param(app_client: TestClient) -> None:
    r = app_client.get("/metrics/summary", params={"window": 3600})
    assert r.status_code == 200
    assert r.json()["window_seconds"] == 3600


def test_metrics_compaction_history(app_client: TestClient) -> None:
    r = app_client.get("/metrics/compaction")
    assert r.status_code == 200
    assert "history" in r.json()
