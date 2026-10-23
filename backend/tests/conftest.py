import asyncio
import os
import secrets
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Tests never use a real key: generate one before the app module (and its settings) loads.
os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.core.config import ROOT_DIR, Settings  # noqa: E402
from backend.app.db.session import create_engine, create_sessionmaker  # noqa: E402
from backend.app.main import create_app  # noqa: E402
from backend.app.services.stories import (  # noqa: E402
    SeedResult,
    load_story_files,
    seed_stories,
)


def migrate(database_url: str) -> None:
    cfg = Config(str(ROOT_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.attributes["configure_logging"] = False
    command.upgrade(cfg, "head")


def sqlite_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


def seed(database_url: str, stories=None) -> SeedResult:
    """Seeds stories on a worker thread (safe even when an event loop is running)."""

    async def run() -> SeedResult:
        engine = create_engine(database_url)
        try:
            async with create_sessionmaker(engine)() as session:
                return await seed_stories(session, stories or load_story_files())
        finally:
            await engine.dispose()

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, run()).result()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    migrate(sqlite_url(path))
    return path


@pytest.fixture
def seeded(db_path: Path) -> Path:
    """The test database with every story file seeded."""
    seed(sqlite_url(db_path))
    return db_path


@pytest.fixture
def settings(db_path: Path) -> Settings:
    return Settings(
        _env_file=None, app_env="test", log_level="WARNING", database_url=sqlite_url(db_path)
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c
