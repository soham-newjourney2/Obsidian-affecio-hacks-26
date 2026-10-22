import pytest
from fastapi.testclient import TestClient

from backend.app.content import profile_options as opts

PROFILE = {
    "interests": ["books", "puzzles", "coffee_tea"],
    "genres": ["mystery"],
    "activities": ["coffee", "walk"],
    "interaction_style": "thoughtful",
    "preferred_roles": ["listener"],
    "availability": ["weekday_evenings"],
    "visibility": "match_only",
    "shareable_summary": "New in town, into puzzles and long walks.",
}


@pytest.fixture
def auth(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": "ada@example.com",
            "password": "correct horse battery",
            "display_name": "Ada",
            "age_confirmed": True,
        },
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def put(client: TestClient, auth: dict, **overrides):
    return client.put("/api/v1/users/me/profile", json={**PROFILE, **overrides}, headers=auth)


def test_profile_missing_until_saved(client: TestClient, auth: dict) -> None:
    res = client.get("/api/v1/users/me/profile", headers=auth)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "PROFILE_NOT_FOUND"


def test_profile_save_and_read(client: TestClient, auth: dict) -> None:
    res = put(client, auth)
    assert res.status_code == 200
    saved = res.json()
    assert {k: saved[k] for k in PROFILE} == PROFILE
    assert client.get("/api/v1/users/me/profile", headers=auth).json() == saved


def test_profile_update_overwrites(client: TestClient, auth: dict) -> None:
    put(client, auth)
    res = put(client, auth, interests=["film", "music", "art_design", "writing"], genres=[])
    assert res.status_code == 200
    body = client.get("/api/v1/users/me/profile", headers=auth).json()
    assert body["interests"] == ["film", "music", "art_design", "writing"]
    assert body["genres"] == []


def test_profile_defaults_and_normalisation(client: TestClient, auth: dict) -> None:
    minimal = {
        "interests": ["books", "books", "film", "music"],
        "interaction_style": "playful",
        "availability": ["weekend_evenings"],
    }
    res = client.put("/api/v1/users/me/profile", json=minimal, headers=auth)
    assert res.status_code == 200
    body = res.json()
    assert body["interests"] == ["books", "film", "music"]  # de-duplicated, order kept
    assert body["visibility"] == "private"  # private by default
    assert body["genres"] == body["activities"] == body["preferred_roles"] == []
    assert body["shareable_summary"] == ""


def test_summary_whitespace_collapsed(client: TestClient, auth: dict) -> None:
    res = put(client, auth, shareable_summary="  Hello \n\n  there  ")
    assert res.json()["shareable_summary"] == "Hello there"


@pytest.mark.parametrize(
    "overrides",
    [
        {"interests": ["books", "film"]},  # below minimum (3)
        {"interests": [i for i, _ in opts.INTERESTS[:9]]},  # above maximum (8)
        {"interests": ["books", "film", "knitting"]},  # unknown interest
        {"genres": ["romance"]},
        {"activities": ["skydiving"]},
        {"preferred_roles": ["detective"]},
        {"preferred_roles": ["listener", "archivist", "strategist"]},  # max 2
        {"availability": []},  # at least one window
        {"availability": ["midnight"]},
        {"interaction_style": "aggressive"},
        {"visibility": "public"},
        {"shareable_summary": "x" * 161},
        {"shareable_summary": "bell\u0007"},
        {"interests": ["books"] * 33},  # raw list cap
        {"user_id": "00000000-0000-0000-0000-000000000000"},  # unknown fields rejected
    ],
)
def test_profile_bounds(client: TestClient, auth: dict, overrides: dict) -> None:
    res = put(client, auth, **overrides)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_profile_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/users/me/profile").status_code == 401
    assert client.put("/api/v1/users/me/profile", json=PROFILE).status_code == 401


def test_profiles_are_per_user(client: TestClient, auth: dict) -> None:
    put(client, auth)
    other = client.post(
        "/api/v1/auth/register",
        json={
            "email": "bo@example.com",
            "password": "correct horse battery",
            "display_name": "Bo",
            "age_confirmed": True,
        },
    ).json()["access_token"]
    res = client.get("/api/v1/users/me/profile", headers={"Authorization": f"Bearer {other}"})
    assert res.status_code == 404


def test_meta_interests_lists_every_option(client: TestClient) -> None:
    res = client.get("/api/v1/meta/interests")
    assert res.status_code == 200
    body = res.json()
    assert [o["id"] for o in body["interests"]] == [i for i, _ in opts.INTERESTS]
    for key in ("genres", "activities", "interaction_styles", "roles", "availability"):
        ids = [o["id"] for o in body[key]]
        assert ids and len(ids) == len(set(ids))
    assert body["limits"]["interests"] == [3, 8]
    assert body["summary_max"] == 160
