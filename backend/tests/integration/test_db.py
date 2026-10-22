from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from backend.app.core.config import ROOT_DIR
from backend.app.db.session import create_engine
from backend.tests.conftest import sqlite_url


def test_migrations_match_models(db_path: Path) -> None:
    cfg = Config(str(ROOT_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", sqlite_url(db_path))
    cfg.attributes["configure_logging"] = False
    command.check(cfg)  # raises if models and migrations have drifted


async def test_sqlite_runs_with_wal_and_foreign_keys(tmp_path: Path) -> None:
    engine = create_engine(sqlite_url(tmp_path / "pragmas.db"))
    try:
        async with engine.connect() as conn:
            assert await conn.scalar(text("PRAGMA journal_mode")) == "wal"
            assert await conn.scalar(text("PRAGMA foreign_keys")) == 1
    finally:
        await engine.dispose()
