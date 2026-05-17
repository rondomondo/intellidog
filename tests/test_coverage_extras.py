"""Additional tests targeting uncovered lines across multiple modules."""
import sqlite3
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.db.repository import (
    insert_alert,
    insert_event,
    insert_log,
    load_rules_from_db,
    query_events,
    query_logs,
    upsert_rule,
)
from src.engine.alert_engine import _evaluate_condition, evaluate_all_rules, load_rules_as_objects
from src.models.alert import Alert, AlertRule, AlertSeverity, RuleCondition
from src.models.event import EventEntry, EventSeverity, EventType, LogEntry, LogLevel


def _make_event(source: str = "svc", severity: str = "high") -> EventEntry:
    return EventEntry(
        source=source,
        event_type=EventType.error,
        severity=EventSeverity(severity),
        message="test",
        timestamp=datetime.now(UTC),
    )


def _make_log(level: str = "ERROR") -> LogEntry:
    return LogEntry(
        host="web-01",
        service="nginx",
        level=LogLevel(level),
        message="test log",
        timestamp=datetime.now(UTC),
    )


# Repository: _now_utc and timestamp filter paths
def test_query_events_since_and_until(db_conn: sqlite3.Connection) -> None:
    insert_event(db_conn, _make_event())
    since = datetime(2000, 1, 1, tzinfo=UTC)
    until = datetime(2099, 12, 31, tzinfo=UTC)
    rows = query_events(db_conn, since=since, until=until)
    assert len(rows) >= 1


def test_query_events_event_type_filter(db_conn: sqlite3.Connection) -> None:
    insert_event(db_conn, _make_event())
    rows = query_events(db_conn, event_type="error")
    assert len(rows) >= 1
    rows_none = query_events(db_conn, event_type="deploy")
    assert len(rows_none) == 0


def test_query_logs_level_filter(db_conn: sqlite3.Connection) -> None:
    insert_log(db_conn, _make_log("INFO"))
    rows = query_logs(db_conn, level="INFO")
    assert len(rows) >= 1
    rows_empty = query_logs(db_conn, level="DEBUG")
    assert len(rows_empty) == 0


def test_query_logs_with_since_until(db_conn: sqlite3.Connection) -> None:
    insert_log(db_conn, _make_log())
    since = datetime(2000, 1, 1, tzinfo=UTC)
    until = datetime(2099, 12, 31, tzinfo=UTC)
    rows = query_logs(db_conn, since=since, until=until)
    assert len(rows) >= 1


def test_query_logs_service_filter(db_conn: sqlite3.Connection) -> None:
    insert_log(db_conn, _make_log())
    rows = query_logs(db_conn, service="nginx")
    assert len(rows) >= 1


def test_load_rules_from_db_empty(db_conn: sqlite3.Connection) -> None:
    rules = load_rules_from_db(db_conn)
    assert rules == []


def test_load_rules_from_db_with_valid_rule(db_conn: sqlite3.Connection) -> None:
    condition = RuleCondition(metric="events_per_minute", operator=">", threshold=10.0, window_seconds=60)
    rule = AlertRule(
        id="test-rule",
        name="Test Rule",
        condition=condition,
        severity=AlertSeverity.high,
        enabled=True,
    )
    upsert_rule(db_conn, rule)
    rules = load_rules_from_db(db_conn)
    assert len(rules) == 1
    assert rules[0].id == "test-rule"


# Alert engine: log_error_rate metric and p95
def test_evaluate_log_error_rate(db_conn: sqlite3.Connection) -> None:
    for _ in range(5):
        insert_log(db_conn, _make_log("ERROR"))
    for _ in range(5):
        insert_log(db_conn, _make_log("INFO"))
    condition = RuleCondition(metric="log_error_rate", operator=">", threshold=30.0, window_seconds=3600)
    triggered, val, details = _evaluate_condition(db_conn, condition)
    assert triggered
    assert val == 50.0
    assert details["total_logs"] == 10


def test_evaluate_p95_no_data(db_conn: sqlite3.Connection) -> None:
    condition = RuleCondition(metric="p95", operator=">", threshold=5000.0, window_seconds=3600)
    triggered, val, _ = _evaluate_condition(db_conn, condition)
    assert not triggered
    assert val == 0.0


def test_evaluate_p95_triggered(db_conn: sqlite3.Connection) -> None:
    for i in range(20):
        insert_event(db_conn, EventEntry(
            source="svc",
            event_type=EventType.error,
            severity=EventSeverity.high,
            message="t",
            payload={"duration_ms": 9000 if i >= 18 else 100},
            timestamp=datetime.now(UTC),
        ))
    condition = RuleCondition(metric="p95", operator=">", threshold=5000.0, window_seconds=3600)
    triggered, val, _ = _evaluate_condition(db_conn, condition)
    assert triggered


def test_evaluate_all_rules_exception_logged(db_conn: sqlite3.Connection) -> None:
    """evaluate_all_rules catches errors per-rule without crashing."""
    rule = AlertRule(
        id="bad-rule",
        name="Bad Rule",
        condition=RuleCondition(metric="events_per_minute", operator=">", threshold=0, window_seconds=60),
        severity=AlertSeverity.high,
        enabled=True,
    )
    upsert_rule(db_conn, rule)
    with patch("src.engine.alert_engine._evaluate_condition", side_effect=RuntimeError("boom")):
        alerts = evaluate_all_rules(db_conn)
    assert alerts == []


def test_load_rules_as_objects(db_conn: sqlite3.Connection) -> None:
    condition = RuleCondition(metric="events_per_minute", operator=">", threshold=10.0, window_seconds=60)
    rule = AlertRule(
        id="obj-rule",
        name="Obj Rule",
        condition=condition,
        severity=AlertSeverity.low,
        enabled=True,
    )
    upsert_rule(db_conn, rule)
    objs = load_rules_as_objects(db_conn)
    assert len(objs) == 1


# Health endpoint: degraded when redis is down
def test_health_degraded_when_redis_down(app_client: TestClient, mock_publisher: MagicMock) -> None:
    mock_publisher.is_connected.return_value = False
    r = app_client.get("/health")
    data = r.json()
    assert data["status"] == "degraded"
    assert data["components"]["redis"] == "error"


def test_health_db_exception_handled(app_client: TestClient) -> None:
    bad_conn = MagicMock()
    bad_conn.execute.side_effect = Exception("DB gone")
    app_client.app.state.db_conn = bad_conn
    r = app_client.get("/health")
    data = r.json()
    assert data["components"]["database"] == "error"


def test_health_redis_exception_handled(app_client: TestClient) -> None:
    bad_pub = MagicMock()
    bad_pub.is_connected.side_effect = Exception("redis gone")
    app_client.app.state.publisher = bad_pub
    r = app_client.get("/health")
    data = r.json()
    assert data["components"]["redis"] == "error"


# Ingest: exception path raises 500
def test_ingest_event_db_error_returns_500(app_client: TestClient) -> None:
    with patch("src.api.ingest.insert_event", side_effect=Exception("db error")):
        payload = {
            "source": "svc",
            "event_type": "error",
            "severity": "high",
            "message": "boom",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        r = app_client.post("/events", json=payload)
    assert r.status_code == 500


def test_ingest_log_db_error_returns_500(app_client: TestClient) -> None:
    with patch("src.api.ingest.insert_log", side_effect=Exception("db error")):
        payload = {
            "host": "web-01",
            "service": "nginx",
            "level": "ERROR",
            "message": "boom",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        r = app_client.post("/logs", json=payload)
    assert r.status_code == 500


def test_ingest_notification_db_error_returns_500(app_client: TestClient) -> None:
    with patch("src.api.ingest.insert_notification", side_effect=Exception("db error")):
        payload = {
            "channel": "slack",
            "source_system": "github",
            "title": "boom",
            "body": "body text",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        r = app_client.post("/notifications", json=payload)
    assert r.status_code == 500


def test_ingest_batch_notifications(app_client: TestClient) -> None:
    batch = [
        {
            "channel": "slack",
            "source_system": f"svc-{i}",
            "title": f"Title {i}",
            "body": "body",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        for i in range(3)
    ]
    r = app_client.post("/notifications", json=batch)
    assert r.status_code == 201
    assert r.json()["accepted"] == 3
