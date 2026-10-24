import socket
import threading
import time
from collections.abc import Callable, Iterator

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, expect

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.tests.conftest import migrate, seed, sqlite_url
from backend.tests.e2e.helpers import session_page, watch_console


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


@pytest.fixture
def console_errors(page: Page) -> list[str]:
    """Collects console errors and uncaught page errors for the test's page."""
    return watch_console(page)


@pytest.fixture
def person(browser: Browser, base_url: str) -> Iterator[Callable[[str], Page]]:
    """Factory: each call is a separate person (own context and sessionStorage) on room.html.
    Each page records console errors (`page.errors`) and WebSocket frames (`page.ws_frames`)."""
    contexts = []

    def make(name: str) -> Page:
        context = browser.new_context(base_url=base_url)
        contexts.append(context)
        page = session_page(context.new_page(), name)
        page.errors = watch_console(page)
        page.ws_frames = []
        page.on(
            "websocket",
            lambda ws: ws.on("framereceived", lambda payload: page.ws_frames.append(str(payload))),
        )
        page.goto("/room.html")
        expect(page.locator("#gate")).to_be_visible()
        return page

    yield make
    for context in contexts:
        context.close()
