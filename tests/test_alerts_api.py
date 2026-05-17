from datetime import UTC, datetime

from fastapi.testclient import TestClient

from src.db.repository import insert_alert, upsert_rule
from src.models.alert import Alert, AlertRule, AlertSeverity, RuleCondition


def _rule() -> AlertRule:
    return AlertRule(
        id="test-rule-1",
        name="Test Rule",
        condition=RuleCondition(metric="events_per_minute", operator=">", threshold=10, window_seconds=60),
        severity=AlertSeverity.high,
        enabled=True,
    )


def _alert(rule_name: str = "Test Rule") -> Alert:
    return Alert(
        rule_id="test-rule-1",
        rule_name=rule_name,
        severity=AlertSeverity.high,
        message="Test alert fired",
        source="engine",
        fired_at=datetime.now(UTC),
    )


def test_get_alerts_empty(app_client: TestClient) -> None:
    r = app_client.get("/alerts")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_get_alerts_returns_inserted(app_client: TestClient, db_conn) -> None:
    insert_alert(db_conn, _alert())
    app_client.app.state.db_conn = db_conn
    r = app_client.get("/alerts")
    assert r.json()["total"] == 1


def test_get_alert_by_id(app_client: TestClient, db_conn) -> None:
    alert = _alert()
    insert_alert(db_conn, alert)
    app_client.app.state.db_conn = db_conn
    r = app_client.get(f"/alerts/{alert.alert_id}")
    assert r.status_code == 200
    assert r.json()["alert_id"] == alert.alert_id


def test_get_alert_not_found(app_client: TestClient) -> None:
    r = app_client.get("/alerts/nonexistent-id")
    assert r.status_code == 404


def test_get_rules_empty(app_client: TestClient) -> None:
    r = app_client.get("/rules")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_create_rule_json(app_client: TestClient) -> None:
    payload = {
        "name": "API Rule",
        "description": "Created via API",
        "condition": {
            "metric": "error_rate",
            "operator": ">",
            "threshold": 25.0,
            "window_seconds": 300,
        },
        "severity": "critical",
        "enabled": True,
    }
    r = app_client.post("/rules", json=payload)
    assert r.status_code == 201
    assert r.json()["name"] == "API Rule"


def test_create_rule_yaml(app_client: TestClient) -> None:
    import yaml

    payload = {
        "name": "YAML Rule",
        "condition": {
            "metric": "events_per_minute",
            "operator": ">",
            "threshold": 5,
            "window_seconds": 60,
        },
        "severity": "medium",
    }
    r = app_client.post(
        "/rules",
        content=yaml.dump(payload).encode(),
        headers={"content-type": "application/yaml"},
    )
    assert r.status_code == 201


def test_create_rule_invalid_body(app_client: TestClient) -> None:
    r = app_client.post("/rules", content=b"not json or yaml {{{{", headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_delete_rule_soft(app_client: TestClient, db_conn) -> None:
    upsert_rule(db_conn, _rule())
    app_client.app.state.db_conn = db_conn
    r = app_client.delete("/rules/test-rule-1")
    assert r.status_code == 200
    assert r.json()["status"] == "disabled"
    row = db_conn.execute("SELECT enabled FROM rules WHERE rule_id='test-rule-1'").fetchone()
    assert row["enabled"] == 0


def test_delete_rule_not_found(app_client: TestClient) -> None:
    r = app_client.delete("/rules/nonexistent")
    assert r.status_code == 404
