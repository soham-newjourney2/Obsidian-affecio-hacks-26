import asyncio
import json
import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.game.engine import GameError
from backend.app.main import create_app
from backend.app.services import game as game_service
from backend.tests.wsutil import Player, connected, next_of

ROUTE = ["c_room", "c_creature", "c_inn"]  # reaches the always-safe ending in every variant


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"register_rate_limit": 1000})


def start_case(client: TestClient, room: dict, players: list[Player]) -> dict:
    for p in players:
        client.post(f"/api/v1/rooms/{room['id']}/ready", json={"ready": True}, headers=p.headers)
    res = client.post(f"/api/v1/rooms/{room['id']}/start", headers=players[0].headers)
    assert res.status_code == 200, res.text
    return res.json()


def vote(ws, view: dict, choice: str, action_id: str | None = None) -> None:
    ws.send_json(
        {
            "type": "game.vote",
            "id": "v",
            "payload": {
                "turn": view["turn"],
                "state_version": view["version"],
                "choice_id": choice,
                "client_action_id": action_id or uuid.uuid4().hex,
            },
        }
    )


def canonical(db: Path) -> dict:
    (state,) = sqlite3.connect(db).execute("SELECT canonical_state FROM game_sessions").fetchone()
    return json.loads(state)


def test_start_creates_session_and_snapshot(client, table, seeded) -> None:
    room, ada, bo, cy, zed = table
    started = start_case(client, room, [ada, bo, cy])
    session_id = started["session_id"]
    assert session_id and started["status"] == "active"

    view = client.get(f"/api/v1/sessions/{session_id}", headers=bo.headers).json()["view"]
    assert view["chapter"]["index"] == 1 and view["chapter"]["total"] == 4
    assert view["chapter"]["title"] == "The Visit"
    assert view["decision"]["id"] == "d1_start" and view["turn"] == 1
    assert len(view["you"]["roles"]) == 1  # 3 players: one core role each
    assert "variant" not in view and "solution" not in json.dumps(view)

    assert client.get(f"/api/v1/sessions/{session_id}", headers=zed.headers).status_code == 403
    missing = client.get(f"/api/v1/sessions/{uuid.uuid4()}", headers=bo.headers)
    assert missing.json()["error"]["code"] == "SESSION_NOT_FOUND"
    rows = sqlite3.connect(seeded).execute("SELECT role FROM room_members WHERE role IS NOT NULL")
    assert sorted(r for (r,) in rows) == ["archivist", "investigator", "listener"]


def test_three_players_play_to_the_end_over_ws(client, table, seeded) -> None:
    room, ada, bo, cy, _ = table
    with (
        connected(client, room["id"], ada) as wa,
        connected(client, room["id"], bo) as wb,
        connected(client, room["id"], cy) as wc,
    ):
        sockets = [wa, wb, wc]
        assert all(ws.snapshot["payload"]["game"] is None for ws in sockets)
        start_case(client, room, [ada, bo, cy])
        views = [next_of(ws, "game.scene")["payload"]["view"] for ws in sockets]
        assert {v["chapter"]["scene_id"] for v in views} == {"s1_visit"}
        for choice in ROUTE:
            for ws, view in zip(sockets, views, strict=True):
                vote(ws, view, choice)
            views = [
                next_of(ws, "game.decision.resolved", choice_id=choice)["payload"]["view"]
                for ws in sockets
            ]
        for ws in sockets:
            done = next_of(ws, "game.completed")
            assert done["payload"]["kind"] == "safe"
            assert done["payload"]["view"]["ending"]["title"] == "A safe retreat"

    db = sqlite3.connect(seeded)
    assert db.execute("SELECT status, outcome FROM game_sessions").fetchone() == (
        "completed",
        "safe",
    )
    assert db.execute("SELECT status FROM rooms").fetchone() == ("completed",)
    assert db.execute("SELECT count(*) FROM votes WHERE status = 'active'").fetchone() == (9,)
    seqs = [s for (s,) in db.execute("SELECT seq FROM game_events ORDER BY seq")]
    assert seqs == list(range(1, len(seqs) + 1))


def test_ws_frames_hold_only_your_own_private_clues(client, table, seeded) -> None:
    room, ada, bo, cy, _ = table
    received: dict[str, list[str]] = {}
    with (
        connected(client, room["id"], ada) as wa,
        connected(client, room["id"], bo) as wb,
        connected(client, room["id"], cy) as wc,
    ):
        sockets = {"ada": wa, "bo": wb, "cy": wc}
        start_case(client, room, [ada, bo, cy])
        views = {}
        for name, ws in sockets.items():
            frame = next_of(ws, "game.scene")
            received[name] = [json.dumps(frame)]
            views[name] = frame["payload"]["view"]
        for name, ws in sockets.items():
            vote(ws, views[name], "c_room")
        for name, ws in sockets.items():
            # Read through the scene change and the room's clue reveals.
            while True:
                frame = ws.receive_json()
                received[name].append(json.dumps(frame))
                if frame["type"] == "game.scene" and frame["payload"]["scene_id"] == "s3_room":
                    break
        members = {name: views[name]["you"]["member_id"] for name in sockets}
    state = canonical(seeded)
    for name, member in members.items():
        blob = "".join(received[name])
        for clue_id, owner in state["clue_owner"].items():
            if owner not in ("public", member):
                assert f'"{clue_id}"' not in blob, (name, clue_id)


def test_private_clue_events_go_to_owner_only(client, table, seeded) -> None:
    room, ada, bo, cy, _ = table
    with connected(client, room["id"], ada) as wa, connected(client, room["id"], bo) as wb:
        start_case(client, room, [ada, bo, cy])
        state = canonical(seeded)
        for ws in (wa, wb):
            me = ws.snapshot["payload"]["you"]
            mine = sorted(
                c for c, o in state["clue_owner"].items() if o == me and c in state["revealed"]
            )
            seen = []
            while len(seen) < len(mine):
                frame = ws.receive_json()
                if frame["type"] == "game.clue.private":
                    seen.append(frame["payload"]["clue_id"])
                    assert frame["payload"]["view"]["you"]["member_id"] == me
            assert sorted(seen) == mine


def test_stale_vote_gets_error_and_snapshot(client, table) -> None:
    room, ada, bo, cy, _ = table
    with (
        connected(client, room["id"], ada) as wa,
        connected(client, room["id"], bo) as wb,
        connected(client, room["id"], cy) as wc,
    ):
        start_case(client, room, [ada, bo, cy])
        views = [next_of(ws, "game.scene")["payload"]["view"] for ws in (wa, wb, wc)]
        for ws, view in zip((wa, wb, wc), views, strict=True):
            vote(ws, view, "c_room")
        next_of(wa, "game.decision.resolved")
        vote(wa, views[0], "c_leak")  # still holding the previous turn's view
        assert next_of(wa, "error")["payload"]["code"] == "STALE_STATE"
        fresh = next_of(wa, "room.snapshot")["payload"]["game"]
        assert fresh["chapter"]["scene_id"] == "s3_room" and fresh["turn"] == 2


def test_duplicate_vote_is_idempotent(client, table, seeded) -> None:
    room, ada, bo, cy, _ = table
    with connected(client, room["id"], ada) as wa:
        start_case(client, room, [ada, bo, cy])
        view = next_of(wa, "game.scene")["payload"]["view"]
        vote(wa, view, "c_room", action_id="same")
        first = next_of(wa, "game.vote.tally")
        vote(wa, view, "c_room", action_id="same")  # a client retry
        vote(wa, view, "c_grounds")  # a later, different vote still arrives normally
        following = next_of(wa, "game.vote.tally")
        assert following["payload"]["tally"] == {"c_grounds": 1}
        assert following["payload"]["state_version"] == first["payload"]["state_version"] + 1
    assert sqlite3.connect(seeded).execute("SELECT count(*) FROM votes").fetchone() == (2,)


def test_invalid_spoofed_and_rate_limited_actions(client, table) -> None:
    room, ada, bo, cy, _ = table
    with connected(client, room["id"], ada) as wa:
        start_case(client, room, [ada, bo, cy])
        view = next_of(wa, "game.scene")["payload"]["view"]
        vote(wa, view, "ending_success")
        assert next_of(wa, "error")["payload"]["code"] == "INVALID_CHOICE"
        spoof = {"client_action_id": "x", "member_id": "someone-else"}
        wa.send_json({"type": "game.hint.request", "id": "h", "payload": spoof})
        assert next_of(wa, "error")["payload"]["code"] == "VALIDATION_ERROR"
        for _ in range(4):
            vote(wa, view, "nope")
        codes = [next_of(wa, "error")["payload"]["code"] for _ in range(4)]
        assert codes[-1] == "RATE_LIMITED"  # 2 actions/s with a small burst


def test_sharing_a_clue_reaches_everyone(client, table, seeded) -> None:
    room, ada, bo, cy, _ = table
    with (
        connected(client, room["id"], ada) as wa,
        connected(client, room["id"], bo) as wb,
        connected(client, room["id"], cy) as wc,
    ):
        start_case(client, room, [ada, bo, cy])
        sockets = {ws.snapshot["payload"]["you"]: ws for ws in (wa, wb, wc)}
        state = canonical(seeded)
        clue, owner = next(
            (c, o)
            for c, o in state["clue_owner"].items()
            if o != "public" and c in state["revealed"]
        )
        share = {"clue_id": clue, "client_action_id": "s1"}
        sockets[owner].send_json({"type": "game.clue.share", "id": "s", "payload": share})
        for ws in sockets.values():
            frame = next_of(ws, "game.board.updated", by=owner)
            assert clue in [c["id"] for c in frame["payload"]["view"]["board"]]


def test_majority_resolves_after_grace(client, table, monkeypatch) -> None:
    monkeypatch.setattr(game_service, "VOTE_GRACE_S", 0.3)
    room, ada, bo, cy, _ = table
    with connected(client, room["id"], ada) as wa, connected(client, room["id"], bo) as wb:
        start_case(client, room, [ada, bo, cy])
        for ws in (wa, wb):
            vote(ws, next_of(ws, "game.scene")["payload"]["view"], "c_room")
        voters = sorted(ws.snapshot["payload"]["you"] for ws in (wa, wb))
        tally = next_of(wa, "game.vote.tally", voted=voters)
        assert tally["payload"]["deadline"] is not None  # 2 of 3 is a majority
        resolved = next_of(wa, "game.decision.resolved")  # delivered by the timer
        assert resolved["payload"]["view"]["chapter"]["scene_id"] == "s3_room"


async def test_concurrent_final_votes_advance_once(settings, seeded, client, table) -> None:
    room, ada, bo, cy, _ = table
    start_case(client, room, [ada, bo, cy])
    members = [s["member_id"] for s in canonical(seeded)["seats"]]
    (raw_id,) = sqlite3.connect(seeded).execute("SELECT id FROM game_sessions").fetchone()
    session_id = uuid.UUID(raw_id)
    # Two app instances = two processes' worth of locks: only the CAS guards the race.
    app_a, app_b = create_app(settings), create_app(settings)
    base = {"type": "vote", "turn": 1, "state_version": 0, "choice_id": "c_room"}

    async def cast(app, member: str, action_id: str):
        try:
            return await game_service.apply_action(
                app, session_id, {**base, "member_id": member, "action_id": action_id}
            )
        except GameError as exc:
            return exc.code

    await cast(app_a, members[0], "a")
    results = await asyncio.gather(
        cast(app_a, members[1], "b"),
        cast(app_b, members[2], "c"),
        cast(app_b, members[1], "b2"),
    )
    for app in (app_a, app_b):
        await app.state.engine.dispose()
    after = canonical(seeded)
    assert after["turn"] == 2 and after["scene"] == "s3_room"  # advanced exactly once
    assert [h["decision_id"] for h in after["history"]] == ["d1_start"]
    assert "STALE_STATE" in results  # whoever came after the resolution was told so
