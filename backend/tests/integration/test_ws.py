import contextlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.core.config import Settings
from backend.app.ws import handlers

PASSWORD = "correct horse battery"


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"register_rate_limit": 1000})


class Player:
    def __init__(self, client: TestClient, name: str) -> None:
        res = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"{name.lower()}@example.com",
                "password": PASSWORD,
                "display_name": name,
                "age_confirmed": True,
            },
        )
        self.name = name
        self.token = res.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}


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


def url(room_id: str) -> str:
    return f"/api/v1/ws/rooms/{room_id}"


def auth_frame(token: str) -> dict:
    return {"type": "auth", "id": "a1", "payload": {"token": token}}


def next_of(ws, type_: str, **match) -> dict:
    """Reads frames until one of `type_` whose payload matches `match` arrives."""
    for _ in range(50):
        frame = ws.receive_json()
        if frame["type"] == type_ and all(frame["payload"].get(k) == v for k, v in match.items()):
            return frame
    raise AssertionError(f"no {type_} {match}")


@contextlib.contextmanager
def connected(client: TestClient, room_id: str, player: Player):
    with client.websocket_connect(url(room_id)) as ws:
        ws.send_json(auth_frame(player.token))
        snapshot = ws.receive_json()
        assert snapshot["type"] == "room.snapshot", snapshot
        ws.snapshot = snapshot
        yield ws


def close_code(ws) -> int:
    with pytest.raises(WebSocketDisconnect) as exc:
        for _ in range(50):
            ws.receive_json()
    return exc.value.code


def chat(ws, body: str, cid: str, ref: str = "c") -> None:
    ws.send_json(
        {"type": "chat.send", "id": ref, "payload": {"client_message_id": cid, "body": body}}
    )


# --- close codes ---------------------------------------------------------------------------


def test_no_auth_in_time_closes_4401(client, table, monkeypatch) -> None:
    monkeypatch.setattr(handlers, "AUTH_TIMEOUT_S", 0.2)
    room = table[0]
    with client.websocket_connect(url(room["id"])) as ws:
        assert close_code(ws) == 4401


@pytest.mark.parametrize(
    "first",
    ids=["chat-first", "bad-token", "no-token", "not-json"],
    argvalues=[
        {"type": "chat.send", "payload": {"client_message_id": "x", "body": "hi"}},
        {"type": "auth", "payload": {"token": "not-a-jwt"}},
        {"type": "auth", "payload": {}},
        "not json",
    ],
)
def test_bad_first_frame_closes_4401(client, table, first) -> None:
    with client.websocket_connect(url(table[0]["id"])) as ws:
        ws.send_text(first if isinstance(first, str) else json.dumps(first))
        assert close_code(ws) == 4401


def test_revoked_token_closes_4401(client, table) -> None:
    room, ada = table[0], table[1]
    client.post("/api/v1/auth/logout", headers=ada.headers)
    with client.websocket_connect(url(room["id"])) as ws:
        ws.send_json(auth_frame(ada.token))
        assert close_code(ws) == 4401


def test_non_member_closes_4403(client, table) -> None:
    room, *_, zed = table
    with client.websocket_connect(url(room["id"])) as ws:
        ws.send_json(auth_frame(zed.token))
        assert close_code(ws) == 4403
    unknown = "00000000-0000-0000-0000-000000000000"
    with client.websocket_connect(url(unknown)) as ws:
        ws.send_json(auth_frame(zed.token))
        assert close_code(ws) == 4403


def test_member_who_left_closes_4403(client, table) -> None:
    room, _, bo, *_ = table
    client.post(f"/api/v1/rooms/{room['id']}/leave", headers=bo.headers)
    with client.websocket_connect(url(room["id"])) as ws:
        ws.send_json(auth_frame(bo.token))
        assert close_code(ws) == 4403


def test_membership_rechecked_on_every_frame(client, table, seeded) -> None:
    room, _, bo, *_ = table
    with connected(client, room["id"], bo) as ws:
        with sqlite3.connect(seeded) as conn:
            conn.execute(
                "UPDATE room_members SET status = 'removed' WHERE user_id IN "
                "(SELECT id FROM users WHERE display_name = 'Bo')"
            )
        chat(ws, "still here?", "m1")
        assert close_code(ws) == 4403


# --- snapshot, presence, room events ----------------------------------------------------


def test_snapshot_on_connect(client, table) -> None:
    room, ada, *_ = table
    with connected(client, room["id"], ada) as ws:
        payload = ws.snapshot["payload"]
        assert [m["display_name"] for m in payload["room"]["members"]] == ["Ada", "Bo", "Cy"]
        assert payload["room"]["you_are_host"] is True
        assert payload["online"] == [payload["you"]]
        assert payload["messages"] == []
        assert set(ws.snapshot) == {"type", "id", "ts", "room_id", "payload"}


def test_presence_online_and_offline(client, table) -> None:
    room, ada, bo, *_ = table
    with connected(client, room["id"], ada) as ws_ada:
        with connected(client, room["id"], bo) as ws_bo:
            bo_id = ws_bo.snapshot["payload"]["you"]
            event = next_of(ws_ada, "room.member", event="online", member_id=bo_id)
            assert bo_id in event["payload"]["online"]
        event = next_of(ws_ada, "room.member", event="offline", member_id=bo_id)
        assert bo_id not in event["payload"]["online"]


def test_rest_changes_reach_sockets(client, table) -> None:
    room, ada, bo, cy, zed = table
    with connected(client, room["id"], ada) as ws:
        res = client.post(
            "/api/v1/rooms/join", json={"code": room["invite_code"]}, headers=zed.headers
        )
        assert res.status_code == 200
        joined = next_of(ws, "room.member", event="joined")
        assert [m["display_name"] for m in joined["payload"]["room"]["members"]][-1] == "Zed"

        client.post(f"/api/v1/rooms/{room['id']}/ready", json={"ready": True}, headers=bo.headers)
        ready = next_of(ws, "room.member", event="ready")
        bo_view = next(m for m in ready["payload"]["room"]["members"] if m["display_name"] == "Bo")
        assert bo_view["status"] == "ready"
        # Views are personal: Ada's copy says she is the host.
        assert ready["payload"]["room"]["you_are_host"] is True

        client.post(f"/api/v1/rooms/{room['id']}/leave", headers=cy.headers)
        left = next_of(ws, "room.member", event="left")
        assert "Cy" not in [m["display_name"] for m in left["payload"]["room"]["members"]]


def test_ready_and_leave_over_socket(client, table) -> None:
    room, ada, bo, *_ = table
    with connected(client, room["id"], ada) as ws_ada:
        with connected(client, room["id"], bo) as ws_bo:
            ws_bo.send_json({"type": "player.ready", "id": "r1", "payload": {"ready": True}})
            event = next_of(ws_ada, "room.member", event="ready")
            assert event["payload"]["member_id"] == ws_bo.snapshot["payload"]["you"]
            ws_bo.send_json({"type": "room.leave", "id": "l1", "payload": {}})
            assert close_code(ws_bo) == 1000
        left = next_of(ws_ada, "room.member", event="left")
        assert [m["display_name"] for m in left["payload"]["room"]["members"]] == ["Ada", "Cy"]
    res = client.get(f"/api/v1/rooms/{room['id']}", headers=bo.headers)
    assert res.status_code == 403


def test_leaving_over_rest_closes_your_sockets(client, table) -> None:
    room, _, bo, *_ = table
    with connected(client, room["id"], bo) as ws:
        client.post(f"/api/v1/rooms/{room['id']}/leave", headers=bo.headers)
        assert close_code(ws) == 1000


# --- chat ---------------------------------------------------------------------------------


def test_chat_reaches_members_and_is_kept(client, table, seeded) -> None:
    room, ada, bo, *_ = table
    with connected(client, room["id"], ada) as ws_ada, connected(client, room["id"], bo) as ws_bo:
        payload = '<img src=x onerror="alert(1)">  hello\x00 \n\n\n\nthere '
        chat(ws_ada, payload, "m-1")
        got = next_of(ws_bo, "chat.message")["payload"]
        assert got["display_name"] == "Ada"
        assert got["body"] == '<img src=x onerror="alert(1)">  hello \n\nthere'  # stored as text
        assert got["client_message_id"] == "m-1"
    with connected(client, room["id"], bo) as ws:
        assert [m["body"][:4] for m in ws.snapshot["payload"]["messages"]] == ["<img"]
    rows = sqlite3.connect(seeded).execute("SELECT count(*) FROM messages").fetchone()[0]
    assert rows == 1


def test_chat_dedupe(client, table, seeded) -> None:
    room, ada, bo, *_ = table
    with connected(client, room["id"], ada) as ws_ada, connected(client, room["id"], bo) as ws_bo:
        chat(ws_bo, "once", "same-id")
        chat(ws_bo, "once", "same-id")  # client retry
        chat(ws_bo, "twice", "other-id")
        first = next_of(ws_ada, "chat.message")["payload"]
        second = next_of(ws_ada, "chat.message")["payload"]
        assert (first["body"], second["body"]) == ("once", "twice")  # no duplicate for others
        acks = [next_of(ws_bo, "chat.message")["payload"]["client_message_id"] for _ in range(3)]
        assert acks == ["same-id", "same-id", "other-id"]  # the sender is told both times
    assert sqlite3.connect(seeded).execute("SELECT count(*) FROM messages").fetchone()[0] == 2


def test_chat_rate_limit(client, table) -> None:
    room, ada, *_ = table
    with connected(client, room["id"], ada) as ws:
        for i in range(6):  # burst of 5, then 1/s
            chat(ws, f"msg {i}", f"id-{i}", ref=f"r{i}")
        delivered = []
        while True:
            frame = ws.receive_json()
            if frame["type"] == "chat.message":
                delivered.append(frame["payload"]["body"])
            elif frame["type"] == "error":
                break
        assert frame["payload"] == {"code": "RATE_LIMITED", "ref_id": "r5"}
        assert delivered == [f"msg {i}" for i in range(5)]


@pytest.mark.parametrize(
    ("frame", "code"),
    ids=["too-large", "not-json", "unknown-type", "blank-body", "bad-client-id", "body-too-long"],
    argvalues=[
        ("x" * (8 * 1024 + 1), "FRAME_TOO_LARGE"),
        ("{not json", "INVALID_FRAME"),
        (json.dumps({"type": "nope", "id": "u1"}), "UNKNOWN_TYPE"),
        (
            json.dumps(
                {
                    "type": "chat.send",
                    "id": "v1",
                    "payload": {"client_message_id": "k", "body": "  "},
                }
            ),
            "VALIDATION_ERROR",
        ),
        (
            json.dumps(
                {
                    "type": "chat.send",
                    "id": "v2",
                    "payload": {"client_message_id": "bad id!", "body": "hi"},
                }
            ),
            "VALIDATION_ERROR",
        ),
        (
            json.dumps(
                {
                    "type": "chat.send",
                    "id": "v3",
                    "payload": {"client_message_id": "k", "body": "x" * 1001},
                }
            ),
            "VALIDATION_ERROR",
        ),
    ],
)
def test_bad_frames_get_errors_and_keep_the_socket(client, table, frame, code) -> None:
    room, ada, *_ = table
    with connected(client, room["id"], ada) as ws:
        ws.send_text(frame)
        err = next_of(ws, "error")
        assert err["payload"]["code"] == code
        chat(ws, "still connected", "after")
        assert next_of(ws, "chat.message")["payload"]["body"] == "still connected"


def test_server_never_trusts_client_identity(client, table) -> None:
    room, ada, bo, *_ = table
    with connected(client, room["id"], ada) as ws_ada, connected(client, room["id"], bo) as ws_bo:
        bo_id = ws_bo.snapshot["payload"]["you"]
        ws_ada.send_json(
            {
                "type": "chat.send",
                "id": "f",
                "payload": {"client_message_id": "f", "body": "hi", "member_id": bo_id},
            }
        )
        assert next_of(ws_ada, "error")["payload"]["code"] == "VALIDATION_ERROR"  # extra field
        chat(ws_ada, "hi", "g")
        msg = next_of(ws_bo, "chat.message")["payload"]
        assert msg["display_name"] == "Ada" and msg["member_id"] != bo_id
