import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn
from playwright.sync_api import Page

from backend.app.core.config import Settings
from backend.app.main import create_app


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Real uvicorn on a free port, with a temp DB and mock AI for later phases."""
    tmp = tmp_path_factory.mktemp("e2e")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp.as_posix()}/e2e.db")
        mp.setenv("AI_PROVIDER", "mock")
        mp.setenv("ENABLE_VOICE_VIDEO", "false")
        mp.setenv("ENABLE_BLOCKCHAIN", "false")
        settings = Settings(_env_file=None, app_env="test", log_level="WARNING")
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
    errors: list[str] = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    return errors
