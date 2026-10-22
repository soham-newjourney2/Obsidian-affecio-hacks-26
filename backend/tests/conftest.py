import os
import secrets
from collections.abc import Iterator
from pathlib import Path

# Tests never use a real key: generate one before the app module (and its settings) loads.
os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.core.config import ROOT_DIR, Settings  # noqa: E402
from backend.app.main import create_app  # noqa: E402


def migrate(database_url: str) -> None:
    cfg = Config(str(ROOT_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.attributes["configure_logging"] = False
    command.upgrade(cfg, "head")


def sqlite_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    migrate(sqlite_url(path))
    return path


@pytest.fixture
def settings(db_path: Path) -> Settings:
    return Settings(
        _env_file=None, app_env="test", log_level="WARNING", database_url=sqlite_url(db_path)
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c
