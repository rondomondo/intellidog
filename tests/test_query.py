from datetime import UTC, datetime

from fastapi.testclient import TestClient


def _seed_events(client: TestClient, count: int = 5) -> list[str]:
    events = [
        {
            "source": f"svc-{i}",
            "event_type": "error" if i % 2 == 0 else "info",
            "severity": "high" if i % 2 == 0 else "info",
            "message": f"Event {i}",
            "payload": {"duration_ms": i * 100},
            "tags": ["test"],
            "timestamp": datetime.now(UTC).isoformat(),
        }
        for i in range(count)
    ]
    r = client.post("/events", json=events)
    return r.json()["event_ids"]


def test_query_events_empty(app_client: TestClient) -> None:
    r = app_client.get("/events")
    assert r.status_code == 200
    data = r.json()
    assert "events" in data
    assert data["total"] == 0


def test_query_events_after_ingest(app_client: TestClient) -> None:
    _seed_events(app_client, 5)
    r = app_client.get("/events")
    assert r.status_code == 200
    assert r.json()["total"] == 5


def test_query_events_filter_severity(app_client: TestClient) -> None:
    _seed_events(app_client, 6)
    r = app_client.get("/events", params={"severity": "high"})
    data = r.json()
    assert all(e["severity"] == "high" for e in data["events"])


def test_query_events_filter_source(app_client: TestClient) -> None:
    _seed_events(app_client, 4)
    r = app_client.get("/events", params={"source": "svc-0"})
    assert r.json()["total"] == 1


def test_query_events_limit(app_client: TestClient) -> None:
    _seed_events(app_client, 10)
    r = app_client.get("/events", params={"limit": 3})
    assert len(r.json()["events"]) == 3


def test_query_logs_empty(app_client: TestClient) -> None:
    r = app_client.get("/logs")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_query_logs_after_ingest(app_client: TestClient) -> None:
    logs = [
        {
            "host": "web-01",
            "service": "nginx",
            "level": "ERROR",
            "message": f"Log {i}",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        for i in range(3)
    ]
    app_client.post("/logs", json=logs)
    r = app_client.get("/logs")
    assert r.json()["total"] == 3


def test_query_notifications_empty(app_client: TestClient) -> None:
    r = app_client.get("/notifications")
    assert r.status_code == 200
    assert r.json()["total"] == 0
