from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.routing import Mount

from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.main import create_app


def _assert_error_shape(res, status: int, code: str) -> None:
    assert res.status_code == status
    body = res.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == res.headers["x-request-id"]


def test_unknown_api_route(client: TestClient) -> None:
    _assert_error_shape(client.get("/api/v1/does-not-exist"), 404, "NOT_FOUND")


def test_method_not_allowed(client: TestClient) -> None:
    _assert_error_shape(client.post("/api/v1/health/live"), 405, "METHOD_NOT_ALLOWED")


class _Body(BaseModel):
    name: str


def _app_with_test_routes(settings: Settings):
    app = create_app(settings)

    @app.get("/api/v1/_boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/api/v1/_app_error")
    async def app_error() -> None:
        raise AppError(409, "CONFLICT_X", "Already done")

    @app.post("/api/v1/_validate")
    async def validate(body: _Body) -> dict:
        return {"ok": True}

    # Move the static mount at "/" back to the end so the test routes are reachable.
    static = next(r for r in app.router.routes if isinstance(r, Mount))
    app.router.routes.remove(static)
    app.router.routes.append(static)
    return app


def test_unhandled_error_hides_internals(settings: Settings) -> None:
    with TestClient(_app_with_test_routes(settings), raise_server_exceptions=False) as c:
        res = c.get("/api/v1/_boom")
    _assert_error_shape(res, 500, "INTERNAL_ERROR")
    assert "secret" not in res.text
    assert "Traceback" not in res.text


def test_app_error(settings: Settings) -> None:
    with TestClient(_app_with_test_routes(settings)) as c:
        res = c.get("/api/v1/_app_error")
    _assert_error_shape(res, 409, "CONFLICT_X")
    assert res.json()["error"]["message"] == "Already done"


def test_validation_error(settings: Settings) -> None:
    with TestClient(_app_with_test_routes(settings)) as c:
        res = c.post("/api/v1/_validate", json={"name": 5})
    _assert_error_shape(res, 422, "VALIDATION_ERROR")
