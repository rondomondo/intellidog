from datetime import UTC, datetime

from fastapi.testclient import TestClient


def _event_payload(**kwargs) -> dict:
    base = {
        "source": "test-service",
        "event_type": "error",
        "severity": "high",
        "message": "Test error event",
        "payload": {"duration_ms": 500},
        "tags": ["test"],
        "timestamp": datetime.now(UTC).isoformat(),
    }
    base.update(kwargs)
    return base


def _log_payload(**kwargs) -> dict:
    base = {
        "host": "web-01",
        "service": "nginx",
        "level": "ERROR",
        "message": "upstream timeout",
        "tags": ["test"],
        "timestamp": datetime.now(UTC).isoformat(),
    }
    base.update(kwargs)
    return base


def _notification_payload(**kwargs) -> dict:
    base = {
        "channel": "slack",
        "source_system": "github",
        "title": "Deploy failed",
        "body": "Job #42 failed",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    base.update(kwargs)
    return base


def test_ingest_single_event(app_client: TestClient) -> None:
    r = app_client.post("/events", json=_event_payload())
    assert r.status_code == 201
    data = r.json()
    assert data["accepted"] == 1
    assert len(data["event_ids"]) == 1


def test_ingest_batch_events(app_client: TestClient) -> None:
    batch = [_event_payload(source=f"svc-{i}") for i in range(5)]
    r = app_client.post("/events", json=batch)
    assert r.status_code == 201
    assert r.json()["accepted"] == 5


def test_ingest_single_log(app_client: TestClient) -> None:
    r = app_client.post("/logs", json=_log_payload())
    assert r.status_code == 201
    assert r.json()["accepted"] == 1


def test_ingest_batch_logs(app_client: TestClient) -> None:
    batch = [_log_payload(host=f"host-{i}") for i in range(3)]
    r = app_client.post("/logs", json=batch)
    assert r.status_code == 201
    assert r.json()["accepted"] == 3


def test_ingest_notification(app_client: TestClient) -> None:
    r = app_client.post("/notifications", json=_notification_payload())
    assert r.status_code == 201
    assert r.json()["accepted"] == 1


def test_ingest_event_invalid_payload(app_client: TestClient) -> None:
    r = app_client.post("/events", json={"not_a_valid": "event"})
    assert r.status_code == 422


def test_ingest_event_naive_timestamp_accepted(app_client: TestClient) -> None:
    payload = _event_payload(timestamp="2026-05-17T10:00:00")
    r = app_client.post("/events", json=payload)
    assert r.status_code == 201


def test_ingest_event_utc_timestamp(app_client: TestClient) -> None:
    payload = _event_payload(timestamp="2026-05-17T10:00:00Z")
    r = app_client.post("/events", json=payload)
    assert r.status_code == 201


def test_publisher_called_on_ingest(app_client: TestClient, mock_publisher) -> None:
    app_client.post("/events", json=_event_payload())
    mock_publisher.publish.assert_called_once()
