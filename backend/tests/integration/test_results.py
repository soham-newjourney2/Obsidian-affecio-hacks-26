import json
import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.core.ratelimit import TokenBucket
from backend.tests.integration.test_game import ROUTE, canonical, start_case, vote
from backend.tests.wsutil import Player, connected, next_of


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"register_rate_limit": 1000})


def finish(client: TestClient, table, seeded: Path) -> tuple[str, dict[str, Player], str]:
    """Plays a full case. One player who holds a clue in chapter 1 pins it and asks for a hint;
    everyone votes together. Returns (session_id, players by name, the sharer's name)."""
    room, ada, bo, cy, _ = table
    players = {"ada": ada, "bo": bo, "cy": cy}
    # One player pins, asks and votes back to back: lift the 2/s game limit (tested elsewhere).
    client.app.state.game_bucket = TokenBucket(rate=1000, burst=1000)
    with (
        connected(client, room["id"], ada) as wa,
        connected(client, room["id"], bo) as wb,
        connected(client, room["id"], cy) as wc,
    ):
        sockets = {"ada": wa, "bo": wb, "cy": wc}
        start_case(client, room, list(players.values()))
        views = {n: next_of(ws, "game.scene")["payload"]["view"] for n, ws in sockets.items()}
        # Roles are random; with 3 players the Investigator has no clue until chapter 3.
        sharer = next(n for n, v in views.items() if v["private_clues"])
        ws = sockets[sharer]
        share = {"clue_id": views[sharer]["private_clues"][0]["id"], "client_action_id": "pin"}
        ws.send_json({"type": "game.clue.share", "id": "s", "payload": share})
        next_of(ws, "game.board.updated", by=views[sharer]["you"]["member_id"])
        ws.send_json({"type": "game.hint.request", "id": "h", "payload": {"client_action_id": "h"}})
        views[sharer] = next_of(ws, "game.hint")["payload"]["view"]
        for choice in ROUTE:
            for name, sock in sockets.items():
                vote(sock, views[name], choice)
            views = {
                n: next_of(sock, "game.decision.resolved", choice_id=choice)["payload"]["view"]
                for n, sock in sockets.items()
            }
        for sock in sockets.values():
            next_of(sock, "game.completed")
    (session_id,) = sqlite3.connect(seeded).execute("SELECT id FROM game_sessions").fetchone()
    return str(uuid.UUID(session_id)), players, sharer


def summary(client, session_id, player):
    return client.get(f"/api/v1/sessions/{session_id}/summary", headers=player.headers)


def test_summary_of_a_finished_case(client, table, seeded) -> None:
    session_id, p, sharer = finish(client, table, seeded)
    res = summary(client, session_id, p[sharer])
    assert res.status_code == 200
    body = res.json()
    assert body["ending"]["kind"] == "safe" and body["ending"]["title"] == "A safe retreat"
    assert body["solution"]
    assert [c["title"] for c in body["chapters"]] == ["The Visit", "The Room", "The Vigil"]
    assert [c["choice"] for c in body["chapters"]] == [
        "Go straight to Marian's room",
        "Something living is sent through it",
        "Take Elinor to the village inn for the night",
    ]
    assert all(c["votes"] == 3 for c in body["chapters"])
    team = body["team"]
    assert (team["chapters"], team["decisions"], team["clues_pinned"], team["hints_used"]) == (
        3,
        3,
        1,
        1,
    )
    assert sorted(len(pl["roles"]) for pl in team["players"]) == [1, 1, 1]
    assert body["you"] == {
        "clues_pinned": 1,
        "hints_asked": 1,
        "votes_matched": 3,
        "decisions_voted": 3,
        "badges": [
            {"id": "clue_sharer", "count": 1},
            {"id": "consensus_builder", "count": 3},
        ],
    }
    assert "Outcome: A safe retreat." in body["recap"]
    assert body["pulse_submitted"] is False


def test_badges_are_personal(client, table, seeded) -> None:
    session_id, p, sharer = finish(client, table, seeded)
    other = next(n for n in p if n != sharer)
    you = summary(client, session_id, p[other]).json()["you"]
    assert you["clues_pinned"] == 0 and you["hints_asked"] == 0
    assert [b["id"] for b in you["badges"]] == ["consensus_builder"]  # no Clue Sharer


def test_reflection_is_built_from_events_only(client, table, seeded) -> None:
    session_id, p, sharer = finish(client, table, seeded)
    before = summary(client, session_id, p[sharer]).json()
    state = canonical(seeded)
    state.update(board=[], history=[], hints_used={}, seats=[])  # wipe the live state
    with sqlite3.connect(seeded) as db:
        db.execute("UPDATE game_sessions SET canonical_state = ?", (json.dumps(state),))
    assert summary(client, session_id, p[sharer]).json() == before


def test_summary_access_rules(client, table, seeded) -> None:
    room, ada, bo, cy, zed = table
    started = start_case(client, room, [ada, bo, cy])
    session_id = started["session_id"]
    res = summary(client, session_id, ada)
    assert res.status_code == 409 and res.json()["error"]["code"] == "SESSION_ACTIVE"
    assert summary(client, session_id, zed).status_code == 403
    assert summary(client, uuid.uuid4(), ada).json()["error"]["code"] == "SESSION_NOT_FOUND"


def pulse(client, session_id, player, **body):
    data = {"play_again": "yes", "ease_of_talking": 4, **body}
    return client.post(f"/api/v1/sessions/{session_id}/pulse", json=data, headers=player.headers)


def test_one_pulse_per_person(client, table, seeded) -> None:
    session_id, p, _ = finish(client, table, seeded)
    assert pulse(client, session_id, p["ada"]).status_code == 201
    again = pulse(client, session_id, p["ada"], play_again="no")
    assert again.status_code == 409 and again.json()["error"]["code"] == "PULSE_ALREADY_SENT"
    assert (
        pulse(client, session_id, p["bo"], play_again="maybe", ease_of_talking=2).status_code == 201
    )
    rows = sqlite3.connect(seeded).execute(
        "SELECT play_again, ease_of_talking FROM pulse_responses ORDER BY created_at"
    )
    assert rows.fetchall() == [("yes", 4), ("maybe", 2)]
    assert summary(client, session_id, p["ada"]).json()["pulse_submitted"] is True
    assert summary(client, session_id, p["cy"]).json()["pulse_submitted"] is False


@pytest.mark.parametrize(
    "body",
    [
        {"ease_of_talking": 0},
        {"ease_of_talking": 6},
        {"play_again": "sometimes"},
        {"mood": "great"},  # nothing beyond the two questions is accepted
    ],
)
def test_pulse_validation(client, table, seeded, body) -> None:
    session_id, p, _ = finish(client, table, seeded)
    res = pulse(client, session_id, p["cy"], **body)
    assert res.status_code == 422


def test_pulse_needs_a_finished_case_and_a_member(client, table, seeded) -> None:
    room, ada, bo, cy, zed = table
    session_id = start_case(client, room, [ada, bo, cy])["session_id"]
    assert pulse(client, session_id, ada).json()["error"]["code"] == "SESSION_ACTIVE"
    assert pulse(client, session_id, zed).status_code == 403
