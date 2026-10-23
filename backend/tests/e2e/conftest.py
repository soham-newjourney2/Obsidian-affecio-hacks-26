import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn
from playwright.sync_api import Page

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.tests.conftest import migrate, seed, sqlite_url


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Real uvicorn on a free port, with a temp DB and mock AI for later phases."""
    database_url = sqlite_url(tmp_path_factory.mktemp("e2e") / "e2e.db")
    migrate(database_url)
    seed(database_url)
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", database_url)
        mp.setenv("AI_PROVIDER", "mock")
        mp.setenv("ENABLE_VOICE_VIDEO", "false")
        mp.setenv("ENABLE_BLOCKCHAIN", "false")
        settings = Settings(
            _env_file=None,
            app_env="test",
            log_level="WARNING",
            # Every e2e test registers from 127.0.0.1; limits are covered by API tests.
            register_rate_limit=10_000,
            login_rate_limit=10_000,
        )
        port = _free_port()
        server = uvicorn.Server(
            uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("live server did not start")
            time.sleep(0.05)
        yield f"http://127.0.0.1:{port}"
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def base_url(live_server: str) -> str:
    return live_server


# API responses that are part of normal flows (browsers log every 4xx fetch as an error).
EXPECTED_HTTP_ERRORS = ("/api/v1/users/me/profile",)  # 404 until onboarding is done


@pytest.fixture
def console_errors(page: Page) -> list[str]:
    """Collects console errors and uncaught page errors for the test's page."""
    errors: list[str] = []

    def on_console(msg) -> None:
        if msg.type != "error":
            return
        url = msg.location.get("url", "")
        if msg.text.startswith("Failed to load resource") and url.endswith(EXPECTED_HTTP_ERRORS):
            return
        errors.append(f"{msg.text} @ {url}")

    page.on("console", on_console)
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    return errors
