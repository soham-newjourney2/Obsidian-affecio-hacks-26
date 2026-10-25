"""P14: AI companions fill seats in demo mode, play along and never decide for humans."""

import sqlite3

import pytest

from backend.app.core.config import Settings
from backend.app.services import ai_hooks, companions
from backend.tests.integration.test_game import ROUTE
from backend.tests.wsutil import Player, connected, next_of


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"register_rate_limit": 1000, "demo_mode": True})


@pytest.fixture
def host_room(client, seeded):
    host = Player(client, "Ada")
    room = client.post(
        "/api/v1/rooms", json={"story_slug": "blackthorn_manor"}, headers=host.headers
    ).json()
    return host, room


def add(client, room, player, count=2):
    return client.post(
        f"/api/v1/rooms/{room['id']}/companions", json={"count": count}, headers=player.headers
    )


def test_companions_are_labelled_and_fill_free_seats(client, host_room) -> None:
    host, room = host_room
    assert room["companions_allowed"] is True
    res = add(client, room, host, count=3)
    assert res.status_code == 200
    members = res.json()["members"]
    assert [(m["display_name"], m["is_companion"], m["status"]) for m in members] == [
        ("Ada", False, "joined"),
        ("Wren", True, "ready"),
        ("Moss", True, "ready"),
        ("Ember", True, "ready"),
    ]
    assert res.json()["companions_allowed"] is False  # table is full
    assert add(client, room, host, 1).json()["error"]["code"] == "ROOM_FULL"


def test_only_the_host_adds_companions(client, host_room) -> None:
    host, room = host_room
    guest = Player(client, "Bo")
    client.post("/api/v1/rooms/join", json={"code": room["invite_code"]}, headers=guest.headers)
    assert add(client, room, guest).json()["error"]["code"] == "NOT_HOST"


def test_flag_off_is_404(client, host_room) -> None:
    host, room = host_room
    client.app.state.settings = client.app.state.settings.model_copy(update={"demo_mode": False})
    assert add(client, room, host).status_code == 404


def test_one_human_and_two_companions_finish_a_case(client, host_room, seeded, monkeypatch):
    monkeypatch.setattr(companions, "COMPANION_DELAY_S", 0)
    host, room = host_room
    add(client, room, host, count=2)
    client.post(f"/api/v1/rooms/{room['id']}/ready", json={"ready": True}, headers=host.headers)
    with connected(client, room["id"], host) as ws:
        started = client.post(f"/api/v1/rooms/{room['id']}/start", headers=host.headers)
        assert started.status_code == 200
        session_id = started.json()["session_id"]
        view = next_of(ws, "game.scene")["payload"]["view"]
        # Companions say one labelled line per scene in chat.
        line = next_of(ws, "chat.message")["payload"]
        assert line["type"] == "companion" and line["display_name"] in ("Wren", "Moss")
        for choice in ROUTE:
            ws.send_json(
                {
                    "type": "game.vote",
                    "id": "v",
                    "payload": {
                        "turn": view["turn"],
                        "state_version": view["version"],
                        "choice_id": choice,
                        "client_action_id": f"h-{choice}",
                    },
                }
            )
            # The companions vote once the human has, with the human: the decision resolves.
            view = next_of(ws, "game.decision.resolved", choice_id=choice)["payload"]["view"]
        assert next_of(ws, "game.completed")["payload"]["kind"] == "safe"
        client.portal.call(ai_hooks.wait_idle, client.app)  # let companion tasks settle

    db = sqlite3.connect(seeded)
    pins = db.execute(
        "SELECT count(*) FROM game_events"
        " WHERE type = 'game.board.updated' AND actor_member_id IS NOT NULL"
    ).fetchone()[0]
    assert pins >= 1  # companions pinned their own clues
    summary = client.get(f"/api/v1/sessions/{session_id}/summary", headers=host.headers).json()
    assert [p["display_name"] for p in summary["team"]["players"]] == ["Ada"]  # humans only
    companion_votes = db.execute(
        "SELECT count(*) FROM votes v JOIN room_members m ON m.id = v.member_id"
        " WHERE m.companion_key IS NOT NULL"
    ).fetchone()[0]
    assert companion_votes == 6  # 2 companions x 3 decisions, each after the human
