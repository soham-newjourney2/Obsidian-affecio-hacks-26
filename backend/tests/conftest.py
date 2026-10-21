import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, app_env="test", log_level="WARNING")


@pytest.fixture
def client(settings: Settings) -> TestClient:
    with TestClient(create_app(settings)) as c:
        yield c
