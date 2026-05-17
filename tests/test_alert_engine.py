import sqlite3
from datetime import UTC, datetime

from src.db.repository import insert_event, upsert_rule
from src.engine.alert_engine import _evaluate_condition, evaluate_all_rules
from src.models.alert import AlertRule, AlertSeverity, RuleCondition
from src.models.event import EventEntry, EventSeverity, EventType


def _make_event(
    source: str = "svc", severity: str = "high", event_type: str = "error", duration_ms: int = 100
) -> EventEntry:
    return EventEntry(
        source=source,
        event_type=EventType(event_type),
        severity=EventSeverity(severity),
        message="test",
        payload={"duration_ms": duration_ms},
        timestamp=datetime.now(UTC),
    )


def _make_rule(metric: str, operator: str, threshold: float, window: int = 60, **kwargs) -> AlertRule:
    condition = RuleCondition(metric=metric, operator=operator, threshold=threshold, window_seconds=window, **kwargs)
    return AlertRule(
        id=f"test-{metric}",
        name=f"Test {metric}",
        condition=condition,
        severity=AlertSeverity.high,
        enabled=True,
    )


def test_evaluate_events_per_minute_not_triggered(db_conn: sqlite3.Connection) -> None:
    rule = _make_rule("events_per_minute", ">", 100, event_type="error")
    triggered, val, _ = _evaluate_condition(db_conn, rule.condition)
    assert not triggered
    assert val == 0.0


def test_evaluate_events_per_minute_triggered(db_conn: sqlite3.Connection) -> None:
    for _ in range(10):
        insert_event(db_conn, _make_event(event_type="error"))
    rule = _make_rule("events_per_minute", ">", 0, event_type="error")
    triggered, val, details = _evaluate_condition(db_conn, rule.condition)
    assert triggered
    assert val > 0
    assert details["count"] == 10


def test_evaluate_error_rate_triggered(db_conn: sqlite3.Connection) -> None:
    for _ in range(8):
        insert_event(db_conn, _make_event(severity="critical"))
    for _ in range(2):
        insert_event(db_conn, _make_event(severity="info"))
    rule = _make_rule("error_rate", ">", 50.0)
    triggered, val, _ = _evaluate_condition(db_conn, rule.condition)
    assert triggered
    assert val > 50.0


def test_evaluate_p99_triggered(db_conn: sqlite3.Connection) -> None:
    for i in range(20):
        insert_event(db_conn, _make_event(duration_ms=9000 if i >= 18 else 100))
    rule = _make_rule("p99", ">", 5000, field="duration_ms")
    triggered, val, _ = _evaluate_condition(db_conn, rule.condition)
    assert triggered


def test_evaluate_p99_not_triggered(db_conn: sqlite3.Connection) -> None:
    for _ in range(10):
        insert_event(db_conn, _make_event(duration_ms=100))
    rule = _make_rule("p99", ">", 5000, field="duration_ms")
    triggered, _, _ = _evaluate_condition(db_conn, rule.condition)
    assert not triggered


def test_evaluate_unknown_operator(db_conn: sqlite3.Connection) -> None:
    rule = _make_rule("events_per_minute", "???", 10)
    triggered, val, _ = _evaluate_condition(db_conn, rule.condition)
    assert not triggered


def test_evaluate_all_rules_no_rules(db_conn: sqlite3.Connection) -> None:
    alerts = evaluate_all_rules(db_conn)
    assert alerts == []


def test_evaluate_all_rules_fires_alert(db_conn: sqlite3.Connection) -> None:
    rule = _make_rule("events_per_minute", ">", 0, event_type="error")
    upsert_rule(db_conn, rule)
    insert_event(db_conn, _make_event(event_type="error"))
    alerts = evaluate_all_rules(db_conn)
    assert len(alerts) == 1
    assert alerts[0].rule_name == rule.name


def test_evaluate_distinct_sources(db_conn: sqlite3.Connection) -> None:
    for i in range(5):
        insert_event(db_conn, _make_event(source=f"svc-{i}"))
    rule = _make_rule("distinct_sources", ">", 3)
    triggered, val, _ = _evaluate_condition(db_conn, rule.condition)
    assert triggered
    assert val == 5.0
