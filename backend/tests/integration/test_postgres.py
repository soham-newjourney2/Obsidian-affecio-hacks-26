"""P20: migrations, seed and the core flows on Postgres.

Runs only when TEST_POSTGRES_URL points at a throwaway database (its public schema is reset):
    uv sync --group postgres
    TEST_POSTGRES_URL=postgresql://user:pass@localhost:5432/echo_test uv run pytest -q -k postgres
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.core.config import Settings
from backend.app.db.session import create_engine
from backend.app.main import create_app
from backend.tests.conftest import migrate, seed
from backend.tests.wsutil import Player, connected, next_of

RAW_URL = os.environ.get("TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not RAW_URL, reason="TEST_POSTGRES_URL not set")


def _reset_schema(url: str) -> None:
    async def run() -> None:
        engine = create_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DROP SCHEMA public CASCADE"))
                await conn.execute(text("CREATE SCHEMA public"))
        finally:
            await engine.dispose()

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, run()).result()


@pytest.fixture
def pg_client():
    settings = Settings(_env_file=None, app_env="test", log_level="WARNING", database_url=RAW_URL)
    _reset_schema(settings.database_url)
    migrate(settings.database_url)
    seed(settings.database_url)
    settings = settings.model_copy(update={"register_rate_limit": 1000, "demo_mode": True})
    with TestClient(create_app(settings)) as client:
        yield client


def test_core_flows_on_postgres(pg_client) -> None:
    client = pg_client
    assert client.get("/api/v1/health/ready").status_code == 200
    stories = client.get("/api/v1/stories").json()
    assert stories[0]["slug"] == "blackthorn_manor" and len(stories) == 5

    ada, bo, cy, dee, eve = (Player(client, n) for n in ("Ada", "Bo", "Cy", "Dee", "Eve"))
    room = client.post(
        "/api/v1/rooms", json={"story_slug": "blackthorn_manor"}, headers=ada.headers
    ).json()
    codes = [
        client.post(
            "/api/v1/rooms/join", json={"code": room["invite_code"]}, headers=p.headers
        ).status_code
        for p in (bo, cy, dee, eve)
    ]
    assert codes == [200, 200, 200, 409]  # capacity 4 incl. host, under the row lock
    client.post(f"/api/v1/rooms/{room['id']}/leave", headers=dee.headers)

    for p in (ada, bo, cy):
        res = client.post(
            f"/api/v1/rooms/{room['id']}/ready", json={"ready": True}, headers=p.headers
        )
        assert res.status_code == 200
    with connected(client, room["id"], bo) as ws:
        started = client.post(f"/api/v1/rooms/{room['id']}/start", headers=ada.headers)
        assert started.status_code == 200
        assert next_of(ws, "game.started")["payload"]["view"]["you"]
    session_id = started.json()["session_id"]
    view = client.get(f"/api/v1/sessions/{session_id}", headers=cy.headers).json()["view"]
    assert view["status"] == "active" and view["chapter"]["title"] == "The Visit"
