from fastapi.testclient import TestClient


def test_health_ok(app_client: TestClient) -> None:
    r = app_client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert "components" in data
    assert data["components"]["database"] == "ok"


def test_health_structure(app_client: TestClient) -> None:
    data = app_client.get("/health").json()
    assert set(data["components"].keys()) == {"database", "redis", "llm"}
