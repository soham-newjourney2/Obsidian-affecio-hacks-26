"""Fixtures shared by integration tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.tests.wsutil import Player


@pytest.fixture
def table(client: TestClient, seeded: Path):
    """A waiting room with Ada (host), Bo and Cy, plus Zed who is not a member."""
    ada, bo, cy, zed = (Player(client, n) for n in ("Ada", "Bo", "Cy", "Zed"))
    room = client.post(
        "/api/v1/rooms", json={"story_slug": "blackthorn_manor"}, headers=ada.headers
    ).json()
    for p in (bo, cy):
        client.post("/api/v1/rooms/join", json={"code": room["invite_code"]}, headers=p.headers)
    return room, ada, bo, cy, zed
