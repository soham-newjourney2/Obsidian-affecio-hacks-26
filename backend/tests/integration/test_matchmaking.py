import time

import pytest

from backend.app.core.config import Settings
from backend.app.services import queue
from backend.tests.wsutil import Player

PROFILE = {
    "interests": ["books", "puzzles", "coffee_tea"],
    "interaction_style": "playful",
    "availability": ["weekend_evenings"],
    "visibility": "match_only",
}


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"register_rate_limit": 1000})


def player(client, name: str, **profile) -> Player:
    p = Player(client, name)
    res = client.put("/api/v1/users/me/profile", json={**PROFILE, **profile}, headers=p.headers)
    assert res.status_code == 200, res.text
    return p


def join(client, p):
    return client.post("/api/v1/matchmaking/queue", headers=p.headers)


def test_three_compatible_players_get_a_room(client, seeded) -> None:
    ada, bo = player(client, "Ada"), player(client, "Bo")
    assert join(client, ada).json()["state"] == "waiting"
    assert join(client, bo).json()["state"] == "waiting"
    cy = player(client, "Cy", visibility="private")
    status = join(client, cy).json()
    assert status["state"] == "matched"
    room_id = status["room_id"]
    for p in (ada, bo):
        s = client.get("/api/v1/matchmaking/status", headers=p.headers).json()
        assert s["state"] == "matched" and s["room_id"] == room_id
        assert "%" not in " ".join(s["explanations"])
    room = client.get(f"/api/v1/rooms/{room_id}", headers=bo.headers).json()
    assert sorted(m["display_name"] for m in room["members"]) == ["Ada", "Bo", "Cy"]
    # Cy chose a private profile: nobody's explanation names Cy's interests, and Cy's own
    # explanation reveals nobody else's.
    assert status["explanations"] == ["A good mix of people for this case"]


def test_status_never_exposes_others(client, seeded) -> None:
    ada = player(client, "Ada")
    body = join(client, ada).json()
    assert set(body) == {"state", "waited_s", "suggest_alternatives"}


def test_profile_required(client, seeded) -> None:
    res = join(client, Player(client, "NoProfile"))
    assert res.status_code == 409 and res.json()["error"]["code"] == "PROFILE_REQUIRED"


def test_leave_and_idle(client, seeded) -> None:
    ada = player(client, "Ada")
    join(client, ada)
    assert client.delete("/api/v1/matchmaking/queue", headers=ada.headers).status_code == 204
    assert client.get("/api/v1/matchmaking/status", headers=ada.headers).json() == {"state": "idle"}


def test_alternatives_offered_after_90s(client, seeded) -> None:
    ada = player(client, "Ada")
    join(client, ada)
    entry = next(iter(client.app.state.queue.entries.values()))
    entry.joined_at = time.monotonic() - queue.SUGGEST_AFTER_S - 1
    s = client.get("/api/v1/matchmaking/status", headers=ada.headers).json()
    assert s["suggest_alternatives"] is True and s["state"] == "waiting"
