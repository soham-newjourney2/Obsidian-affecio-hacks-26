from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def test_live(client: TestClient) -> None:
    res = client.get("/api/v1/health/live")
    assert res.status_code == 200
    assert res.json() == {"status": "live"}
    assert len(res.headers["x-request-id"]) == 32


def test_ready(client: TestClient) -> None:
    res = client.get("/api/v1/health/ready")
    assert res.status_code == 200
    assert res.json() == {"status": "ready"}


def test_ready_fails_without_frontend(tmp_path, monkeypatch) -> None:
    settings = Settings(_env_file=None, app_env="test", frontend_dir=tmp_path)
    monkeypatch.setattr("backend.app.api.v1.health.get_settings", lambda: settings)
    with TestClient(create_app(settings)) as c:
        res = c.get("/api/v1/health/ready")
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "NOT_READY"


def test_request_ids_are_unique_and_not_client_controlled(client: TestClient) -> None:
    a = client.get("/api/v1/health/live", headers={"X-Request-ID": "attacker"})
    b = client.get("/api/v1/health/live")
    assert a.headers["x-request-id"] != "attacker"
    assert a.headers["x-request-id"] != b.headers["x-request-id"]
