import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.core.security import create_access_token

PASSWORD = "correct horse battery"


def register(client: TestClient, email="ada@example.com", password=PASSWORD, name="Ada", **extra):
    body = {"email": email, "password": password, "display_name": name, "age_confirmed": True}
    return client.post("/api/v1/auth/register", json={**body, **extra})


def login(client: TestClient, email="ada@example.com", password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def me(client: TestClient, token: str):
    return client.get("/api/v1/auth/me", headers=bearer(token))


def test_register_login_me_logout(client: TestClient) -> None:
    res = register(client, email="  Ada@Example.COM ")
    assert res.status_code == 201
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert body["user"]["email"] == "ada@example.com"
    assert body["user"]["display_name"] == "Ada"
    assert set(body["user"]) == {"id", "email", "display_name", "created_at"}

    res = login(client, email="ADA@example.com")
    assert res.status_code == 200
    token = res.json()["access_token"]

    res = me(client, token)
    assert res.status_code == 200
    assert res.json()["id"] == body["user"]["id"]

    assert client.post("/api/v1/auth/logout", headers=bearer(token)).status_code == 204
    assert me(client, token).status_code == 401
    # A fresh login still works after logout.
    assert me(client, login(client).json()["access_token"]).status_code == 200


def test_register_token_is_usable(client: TestClient) -> None:
    token = register(client).json()["access_token"]
    assert me(client, token).status_code == 200


@pytest.mark.parametrize("second", ["ada@example.com", "ADA@EXAMPLE.COM", " ada@Example.com "])
def test_duplicate_normalized_email_rejected(client: TestClient, second: str) -> None:
    assert register(client, email="Ada@example.com").status_code == 201
    res = register(client, email=second, name="Other")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "EMAIL_TAKEN"


@pytest.mark.parametrize(
    "overrides",
    [
        {"age_confirmed": False},
        {"password": "short"},
        {"password": "x" * 129},
        {"display_name": "A"},
        {"display_name": "A" * 25},
        {"display_name": "<script>"},
        {"email": "not-an-email"},
        {"status": "active"},  # unknown fields are rejected, not ignored
    ],
)
def test_register_validation(client: TestClient, overrides: dict) -> None:
    body = {
        "email": "ada@example.com",
        "password": PASSWORD,
        "display_name": "Ada",
        "age_confirmed": True,
        **overrides,
    }
    res = client.post("/api/v1/auth/register", json=body)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_login_error_is_generic(client: TestClient) -> None:
    register(client)
    wrong_password = login(client, password="wrong password!")
    unknown_email = login(client, email="nobody@example.com")
    malformed_email = login(client, email="nobody")
    for res in (wrong_password, unknown_email, malformed_email):
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"
        assert res.json()["error"]["message"] == "Incorrect email or password."


def test_password_hash_never_returned(client: TestClient, db_path: Path) -> None:
    responses = [register(client), login(client)]
    responses.append(me(client, responses[-1].json()["access_token"]))
    stored_hash = sqlite3.connect(db_path).execute("SELECT password_hash FROM users").fetchone()[0]
    assert stored_hash.startswith("$argon2")
    for res in responses:
        assert "password" not in res.text
        assert "argon2" not in res.text
        assert stored_hash not in res.text


def test_login_rate_limited_per_ip_and_email(client: TestClient) -> None:
    register(client)
    for _ in range(10):
        assert login(client, password="wrong password!").status_code == 401
    res = login(client)
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "RATE_LIMITED"
    assert int(res.headers["retry-after"]) > 0
    # Another email from the same IP is a different bucket.
    assert login(client, email="other@example.com").status_code == 401


def test_register_rate_limited_per_ip(client: TestClient) -> None:
    for i in range(5):
        assert register(client, email=f"user{i}@example.com").status_code == 201
    res = register(client, email="user5@example.com")
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "RATE_LIMITED"


def _assert_unauthorized(res) -> None:
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"
    assert res.headers["www-authenticate"] == "Bearer"


def test_me_requires_token(client: TestClient) -> None:
    _assert_unauthorized(client.get("/api/v1/auth/me"))
    _assert_unauthorized(client.get("/api/v1/auth/me", headers={"Authorization": "Basic abc"}))
    _assert_unauthorized(me(client, "not.a.jwt"))


def test_expired_token_rejected(client: TestClient, settings: Settings) -> None:
    user_id = uuid.UUID(register(client).json()["user"]["id"])
    secret = settings.secret_key.get_secret_value()
    expired = create_access_token(user_id, secret, minutes=-1).token
    _assert_unauthorized(me(client, expired))


def test_token_with_wrong_secret_rejected(client: TestClient) -> None:
    user_id = uuid.UUID(register(client).json()["user"]["id"])
    forged = create_access_token(user_id, "x" * 48, minutes=5).token
    _assert_unauthorized(me(client, forged))


def test_token_for_unknown_user_rejected(client: TestClient, settings: Settings) -> None:
    token = create_access_token(uuid.uuid4(), settings.secret_key.get_secret_value(), 5).token
    _assert_unauthorized(me(client, token))


def test_suspended_user_locked_out(client: TestClient, db_path: Path) -> None:
    token = register(client).json()["access_token"]
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE users SET status = 'suspended'")
    _assert_unauthorized(me(client, token))
    assert login(client).status_code == 401


def test_logout_requires_token(client: TestClient) -> None:
    _assert_unauthorized(client.post("/api/v1/auth/logout"))
