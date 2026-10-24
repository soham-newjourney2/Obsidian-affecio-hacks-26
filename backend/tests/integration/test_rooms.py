import asyncio
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.services.rooms import hash_invite_code, normalize_invite_code

PASSWORD = "correct horse battery"


@pytest.fixture
def settings(settings: Settings) -> Settings:
    # These tests seat many users from one test IP; registration limits are tested elsewhere.
    return settings.model_copy(update={"register_rate_limit": 1000})


def register(client: TestClient, name: str) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{name.lower()}@example.com",
            "password": PASSWORD,
            "display_name": name,
            "age_confirmed": True,
        },
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def host(client: TestClient, seeded: Path) -> dict[str, str]:
    return register(client, "Host")


def create(client: TestClient, auth: dict, slug: str = "blackthorn_manor"):
    return client.post("/api/v1/rooms", json={"story_slug": slug}, headers=auth)


def join(client: TestClient, auth: dict, code: str):
    return client.post("/api/v1/rooms/join", json={"code": code}, headers=auth)


def act(client: TestClient, auth: dict, room_id: str, action: str, **body):
    return client.post(f"/api/v1/rooms/{room_id}/{action}", json=body or None, headers=auth)


def get(client: TestClient, auth: dict, room_id: str):
    return client.get(f"/api/v1/rooms/{room_id}", headers=auth)


def full_table(client: TestClient, host: dict, players: int = 3):
    """Creates a room and seats `players` humans (host included). Returns (room, code, auths)."""
    created = create(client, host).json()
    auths = [host] + [register(client, f"Player{i}") for i in range(1, players)]
    for auth in auths[1:]:
        assert join(client, auth, created["invite_code"]).status_code == 200
    return created, created["invite_code"], auths


def test_create_room(client: TestClient, host: dict) -> None:
    res = create(client, host)
    assert res.status_code == 201
    body = res.json()
    assert re.fullmatch(r"[A-Z2-7]{8}", body["invite_code"])
    assert body["status"] == "waiting"
    assert body["story"]["title"] == "Blackthorn Manor"
    assert body["you_are_host"] is True
    assert body["can_start"] is False
    assert [(m["display_name"], m["is_host"], m["is_you"]) for m in body["members"]] == [
        ("Host", True, True)
    ]
    assert "invite_hash" not in res.text and "user_id" not in res.text


def test_invite_code_stored_only_as_hash(client: TestClient, host: dict, seeded: Path) -> None:
    code = create(client, host).json()["invite_code"]
    (stored,) = sqlite3.connect(seeded).execute("SELECT invite_hash FROM rooms").fetchone()
    assert stored == hash_invite_code(code)
    assert code not in stored


def test_create_room_story_checks(client: TestClient, host: dict) -> None:
    assert create(client, host, "nope").json()["error"]["code"] == "STORY_NOT_FOUND"
    res = create(client, host, "rue_morgue")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "STORY_NOT_PLAYABLE"


def test_join_normalizes_code(client: TestClient, host: dict) -> None:
    created = create(client, host).json()
    code = created["invite_code"]
    messy = f" {code[:4].lower()}-{code[4:]} "
    guest = register(client, "Guest")
    res = join(client, guest, messy)
    assert res.status_code == 200
    assert [m["display_name"] for m in res.json()["members"]] == ["Host", "Guest"]
    assert res.json()["you_are_host"] is False
    assert normalize_invite_code("ab0c-1d8e") == "ABOCIDBE"


def test_double_join_is_idempotent(client: TestClient, host: dict, seeded: Path) -> None:
    created = create(client, host).json()
    guest = register(client, "Guest")
    assert join(client, guest, created["invite_code"]).status_code == 200
    assert join(client, guest, created["invite_code"]).status_code == 200
    assert join(client, host, created["invite_code"]).status_code == 200
    count = sqlite3.connect(seeded).execute("SELECT count(*) FROM room_members").fetchone()[0]
    assert count == 2


def test_room_full(client: TestClient, host: dict) -> None:
    _, code, _ = full_table(client, host, players=4)
    res = join(client, register(client, "Fifth"), code)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "ROOM_FULL"


async def test_concurrent_joins_never_exceed_capacity(settings: Settings, seeded: Path) -> None:
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:

        async def signup(name: str) -> dict[str, str]:
            res = await ac.post(
                "/api/v1/auth/register",
                json={
                    "email": f"{name}@example.com",
                    "password": PASSWORD,
                    "display_name": name,
                    "age_confirmed": True,
                },
            )
            return {"Authorization": f"Bearer {res.json()['access_token']}"}

        host_auth = await signup("host")
        story = {"story_slug": "blackthorn_manor"}
        created = (await ac.post("/api/v1/rooms", json=story, headers=host_auth)).json()
        guests = [await signup(f"guest{i}") for i in range(5)]
        results = await asyncio.gather(
            *(
                ac.post("/api/v1/rooms/join", json={"code": created["invite_code"]}, headers=g)
                for g in guests
            )
        )
    await app.state.engine.dispose()

    statuses = sorted(r.status_code for r in results)
    # Capacity 4 with the host seated: exactly 3 of the 5 simultaneous joins get in.
    assert statuses == [200, 200, 200, 409, 409]
    assert all(r.json()["error"]["code"] == "ROOM_FULL" for r in results if r.status_code == 409)
    count = (
        sqlite3.connect(seeded)
        .execute("SELECT count(*) FROM room_members WHERE status = 'joined'")
        .fetchone()[0]
    )
    assert count == 4


def test_unknown_expired_and_revoked_codes(client: TestClient, host: dict, seeded: Path) -> None:
    guest = register(client, "Guest")
    for code in ("AAAAAAAA", "not a code"):
        res = join(client, guest, code)
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "INVITE_INVALID"

    expired = create(client, host).json()
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    with sqlite3.connect(seeded) as conn:
        room_id = expired["id"].replace("-", "")
        conn.execute("UPDATE rooms SET expires_at = ? WHERE id = ?", (past, room_id))
    assert join(client, guest, expired["invite_code"]).json()["error"]["code"] == "INVITE_INVALID"

    room, code, auths = full_table(client, host)
    for auth in auths:
        act(client, auth, room["id"], "ready", ready=True)
    assert act(client, host, room["id"], "start").status_code == 200
    res = join(client, register(client, "Late"), code)
    assert res.json()["error"]["code"] == "INVITE_INVALID"  # revoked on start


def test_non_member_is_forbidden(client: TestClient, host: dict) -> None:
    room = create(client, host).json()
    stranger = register(client, "Stranger")
    for res in (
        get(client, stranger, room["id"]),
        act(client, stranger, room["id"], "ready", ready=True),
        act(client, stranger, room["id"], "start"),
        act(client, stranger, room["id"], "leave"),
    ):
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "NOT_A_MEMBER"
    assert get(client, stranger, "00000000-0000-0000-0000-000000000000").status_code == 404


def test_rooms_require_auth(client: TestClient, seeded: Path) -> None:
    story = {"story_slug": "blackthorn_manor"}
    assert client.post("/api/v1/rooms", json=story).status_code == 401
    assert client.post("/api/v1/rooms/join", json={"code": "AAAAAAAA"}).status_code == 401


def test_ready_and_start(client: TestClient, host: dict) -> None:
    room, _, auths = full_table(client, host)
    guest = auths[1]
    assert act(client, guest, room["id"], "start").json()["error"]["code"] == "NOT_HOST"
    assert act(client, host, room["id"], "start").json()["error"]["code"] == "NOT_ALL_READY"
    for auth in auths:
        body = act(client, auth, room["id"], "ready", ready=True).json()
    assert body["can_start"] is False  # only the host can start
    assert get(client, host, room["id"]).json()["can_start"] is True

    act(client, guest, room["id"], "ready", ready=False)
    assert get(client, host, room["id"]).json()["can_start"] is False
    act(client, guest, room["id"], "ready", ready=True)

    res = act(client, host, room["id"], "start")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "active"
    assert {m["status"] for m in body["members"]} == {"playing"}
    assert body["invite_expires_at"] is None
    assert act(client, host, room["id"], "start").json()["error"]["code"] == "ROOM_NOT_WAITING"
    assert act(client, guest, room["id"], "ready", ready=False).status_code == 409


def test_start_needs_three_players(client: TestClient, host: dict) -> None:
    room, _, auths = full_table(client, host, players=2)
    for auth in auths:
        act(client, auth, room["id"], "ready", ready=True)
    res = act(client, host, room["id"], "start")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "NOT_ENOUGH_PLAYERS"


def test_actions_after_leave_rejected(client: TestClient, host: dict) -> None:
    room, code, auths = full_table(client, host)
    guest = auths[1]
    assert act(client, guest, room["id"], "leave").status_code == 204
    assert get(client, guest, room["id"]).status_code == 403
    assert act(client, guest, room["id"], "ready", ready=True).status_code == 403
    assert act(client, guest, room["id"], "leave").status_code == 403
    names = [m["display_name"] for m in get(client, host, room["id"]).json()["members"]]
    assert "Player1" not in names
    # Rejoining while the room still waits is allowed.
    assert join(client, guest, code).status_code == 200


def test_host_leaving_hands_over_then_last_out_abandons(
    client: TestClient, host: dict, seeded: Path
) -> None:
    room, _, auths = full_table(client, host, players=2)
    guest = auths[1]
    act(client, host, room["id"], "leave")
    body = get(client, guest, room["id"]).json()
    assert body["you_are_host"] is True
    assert [m["display_name"] for m in body["members"]] == ["Player1"]
    act(client, guest, room["id"], "leave")
    (status, invite) = (
        sqlite3.connect(seeded).execute("SELECT status, invite_hash FROM rooms").fetchone()
    )
    assert (status, invite) == ("abandoned", None)


def test_join_attempts_are_rate_limited(client: TestClient, host: dict) -> None:
    guesser = register(client, "Guesser")
    for _ in range(20):
        assert join(client, guesser, "AAAAAAAA").status_code == 404
    res = join(client, guesser, "AAAAAAAA")
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "RATE_LIMITED"
