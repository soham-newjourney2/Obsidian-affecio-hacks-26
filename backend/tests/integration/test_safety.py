"""Mutual-opt-in connections, blocks and reports."""

import pytest

from backend.app.core.config import Settings
from backend.tests.integration.test_matchmaking import join, player
from backend.tests.integration.test_results import finish

API = "/api/v1"


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"register_rate_limit": 1000, "admin_emails": "admin@example.com"}
    )


@pytest.fixture
def done(client, table, seeded):
    """A finished case: (session_id, players by name, user ids by name)."""
    session_id, players, _ = finish(client, table, seeded)
    summary = client.get(f"{API}/sessions/{session_id}/summary", headers=players["ada"].headers)
    ids = {p["display_name"].lower(): p["user_id"] for p in summary.json()["team"]["players"]}
    return session_id, players, ids


def ask(client, session_id, frm, to_id):
    return client.post(
        f"{API}/sessions/{session_id}/connections", json={"user_id": to_id}, headers=frm.headers
    )


def mine(client, p):
    return client.get(f"{API}/users/me/connections", headers=p.headers).json()


def test_both_must_accept(client, done) -> None:
    session_id, players, ids = done
    ada, bo = players["ada"], players["bo"]
    assert ask(client, session_id, ada, ids["bo"]).json() == {"state": "requested"}
    assert mine(client, ada)["connections"] == []
    incoming = mine(client, bo)["incoming"]
    assert [r["display_name"] for r in incoming] == ["Ada"]
    accepted = client.post(
        f"{API}/connections/{incoming[0]['request_id']}/accept", headers=bo.headers
    )
    assert accepted.status_code == 204
    (conn,) = mine(client, ada)["connections"]
    assert set(conn) == {"user_id", "display_name", "shareable_summary"}  # nothing else leaks
    assert conn["display_name"] == "Bo"


def test_mutual_request_connects_at_once(client, done) -> None:
    session_id, players, ids = done
    ask(client, session_id, players["ada"], ids["cy"])
    assert ask(client, session_id, players["cy"], ids["ada"]).json() == {"state": "connected"}
    assert [c["display_name"] for c in mine(client, players["ada"])["connections"]] == ["Cy"]


def test_decline_is_not_exposed(client, done) -> None:
    session_id, players, ids = done
    ask(client, session_id, players["ada"], ids["bo"])
    before = mine(client, players["ada"])
    (req,) = mine(client, players["bo"])["incoming"]
    client.post(f"{API}/connections/{req['request_id']}/decline", headers=players["bo"].headers)
    assert mine(client, players["ada"]) == before  # still just "waiting on them"
    assert mine(client, players["bo"])["incoming"] == []
    # Only the recipient can answer.
    res = client.post(
        f"{API}/connections/{req['request_id']}/accept", headers=players["ada"].headers
    )
    assert res.status_code == 404


def test_only_co_players_of_a_finished_case(client, table, done) -> None:
    session_id, players, ids = done
    zed = table[4]
    assert ask(client, session_id, zed, ids["ada"]).status_code == 409  # never sat at the table
    me = client.get(f"{API}/auth/me", headers=zed.headers).json()
    res = ask(client, session_id, players["ada"], me["id"])
    assert res.status_code == 409 and res.json()["error"]["code"] == "CONNECTION_UNAVAILABLE"


def test_block_stops_requests(client, done) -> None:
    session_id, players, ids = done
    ada, bo = players["ada"], players["bo"]
    ask(client, session_id, bo, ids["ada"])
    assert client.post(f"{API}/users/{ids['bo']}/block", headers=ada.headers).status_code == 204
    assert mine(client, ada)["incoming"] == []  # the pending request was withdrawn
    for frm, to in ((ada, "bo"), (bo, "ada")):
        res = ask(client, session_id, frm, ids[to])
        assert res.status_code == 409 and res.json()["error"]["code"] == "CONNECTION_UNAVAILABLE"


def test_block_keeps_people_apart_in_matching(client, seeded) -> None:
    people = [player(client, n) for n in ("Ada", "Bo", "Cy")]
    bo_id = client.get(f"{API}/auth/me", headers=people[1].headers).json()["id"]
    client.post(f"{API}/users/{bo_id}/block", headers=people[0].headers)
    states = [join(client, p).json()["state"] for p in people]
    assert states == ["waiting"] * 3  # the only trio holds a blocked pair
    dee = player(client, "Dee")
    assert join(client, dee).json()["state"] == "matched"
    matched = [
        client.get(f"{API}/matchmaking/status", headers=p.headers).json()["state"] for p in people
    ]
    assert matched == ["matched", "waiting", "matched"]  # Ada, Cy and Dee; never Ada with Bo


def test_reports_are_stored_and_admin_only(client, table, seeded) -> None:
    room, ada, bo, _, _ = table
    bo_id = client.get(f"{API}/auth/me", headers=bo.headers).json()["id"]
    body = {"reported_user": bo_id, "room_id": room["id"], "category": "harassment"}
    res = client.post(f"{API}/reports", json=body, headers=ada.headers)
    assert res.status_code == 201 and res.json()["status"] == "open"
    bad = client.post(f"{API}/reports", json={**body, "category": "nope"}, headers=ada.headers)
    assert bad.status_code == 422
    assert client.get(f"{API}/admin/reports", headers=ada.headers).status_code == 403
    admin = player(client, "Admin")
    (row,) = client.get(f"{API}/admin/reports", headers=admin.headers).json()
    assert row["category"] == "harassment" and row["reported_user"] == bo_id
