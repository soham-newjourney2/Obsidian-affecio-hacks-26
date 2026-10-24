"""Shared helpers for WebSocket tests (TestClient sessions)."""

import contextlib

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

PASSWORD = "correct horse battery"


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
