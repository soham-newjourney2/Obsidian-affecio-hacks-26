"""P17: optional voice/video — room-scoped JaaS tokens for present members only."""

import time
import uuid
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.services.media import TOKEN_TTL_S

APP_ID = "vpaas-magic-cookie-test"


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def settings(settings: Settings, tmp_path: Path, rsa_key) -> Settings:
    """Voice/video on, with a throwaway key generated at runtime (rule 10)."""
    key_path = tmp_path / "jaas.pem"
    key_path.write_bytes(
        rsa_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return settings.model_copy(
        update={
            "register_rate_limit": 1000,
            "enable_voice_video": True,
            "jaas_app_id": APP_ID,
            "jaas_key_id": f"{APP_ID}/abc123",
            "jaas_private_key_path": key_path,
        }
    )


def token_for(client, room, player):
    return client.post(f"/api/v1/rooms/{room['id']}/media-token", headers=player.headers)


def decode(rsa_key, token: str) -> dict:
    return jwt.decode(token, rsa_key.public_key(), algorithms=["RS256"], audience="jitsi")


def test_member_token_claims(client, table, rsa_key) -> None:
    room, ada, bo, _cy, _zed = table
    assert room["media_allowed"] is True
    before = int(time.time())
    res = token_for(client, room, bo)
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "token": body["token"],
        "room": room["id"],
        "app_id": APP_ID,
        "domain": "8x8.vc",
    }
    assert jwt.get_unverified_header(body["token"])["kid"] == f"{APP_ID}/abc123"
    claims = decode(rsa_key, body["token"])
    assert (claims["iss"], claims["sub"], claims["room"]) == ("chat", APP_ID, room["id"])
    assert before <= claims["iat"] and claims["exp"] - claims["iat"] <= 2 * 60 * 60
    assert claims["exp"] - claims["iat"] == TOKEN_TTL_S
    user = claims["context"]["user"]
    assert (user["name"], user["moderator"]) == ("Bo", "false")
    assert set(claims["context"]["features"].values()) == {"false"}
    for feature in ("recording", "livestreaming", "transcription"):
        assert claims["context"]["features"][feature] == "false"


def test_host_is_moderator(client, table, rsa_key) -> None:
    room, ada, *_ = table
    claims = decode(rsa_key, token_for(client, room, ada).json()["token"])
    assert claims["context"]["user"]["moderator"] == "true"


def test_non_member_and_left_member_rejected(client, table) -> None:
    room, _ada, bo, _cy, zed = table
    assert token_for(client, room, zed).status_code == 403
    client.post(f"/api/v1/rooms/{room['id']}/leave", headers=bo.headers)
    res = token_for(client, room, bo)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "NOT_A_MEMBER"


def test_unknown_room_and_anonymous(client, table) -> None:
    _room, ada, *_ = table
    res = client.post(f"/api/v1/rooms/{uuid.uuid4()}/media-token", headers=ada.headers)
    assert res.status_code == 404
    assert client.post(f"/api/v1/rooms/{uuid.uuid4()}/media-token").status_code == 401


def test_unreadable_key_is_503(settings, table, tmp_path) -> None:
    broken = settings.model_copy(update={"jaas_private_key_path": tmp_path / "missing.pem"})
    room, ada, *_ = table
    with TestClient(create_app(broken)) as client:
        res = token_for(client, room, ada)
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "MEDIA_UNAVAILABLE"


def test_flag_off_is_404_and_hidden(settings, table) -> None:
    off = settings.model_copy(update={"enable_voice_video": False})
    room, ada, *_ = table
    with TestClient(create_app(off)) as client:
        assert token_for(client, room, ada).status_code == 404
        view = client.get(f"/api/v1/rooms/{room['id']}", headers=ada.headers).json()
    assert view["media_allowed"] is False
