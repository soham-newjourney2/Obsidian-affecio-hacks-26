"""Fixtures shared by unit tests."""

from pathlib import Path

import pytest

from backend.app.db.session import create_engine, create_sessionmaker
from backend.tests.conftest import sqlite_url


@pytest.fixture
async def maker(db_path: Path):
    """A session factory on a fresh migrated database (for code that logs to ai_logs)."""
    engine = create_engine(sqlite_url(db_path))
    yield create_sessionmaker(engine)
    await engine.dispose()
