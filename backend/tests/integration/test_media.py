from pathlib import Path

import jwt
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app

PASSWORD = "correct horse battery"


def register(client: TestClient, name: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{name.lower()}@example.com",
            "password": PASSWORD,
            "display_name": name,
            "age_confirmed": True,
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_media_token_is_disabled_by_default(client: TestClient, seeded: Path) -> None:
    host = register(client, "Host")
    room = client.post(
        "/api/v1/rooms", json={"story_slug": "blackthorn_manor"}, headers=host
    ).json()
    response = client.post(
        f"/api/v1/rooms/{room['id']}/media-token", headers=host
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MEDIA_DISABLED"


def test_media_token_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/v1/rooms/00000000-0000-0000-0000-000000000001/media-token")
    assert response.status_code == 401


def test_media_token_is_room_scoped_and_host_is_moderator(
    tmp_path: Path, settings: Settings, seeded: Path
) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "jaas-private.pem"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    configured = settings.model_copy(
        update={
            "enable_voice_video": True,
            "jaas_app_id": "test-app",
            "jaas_key_id": "test-key-id",
            "jaas_private_key_path": key_path,
            "register_rate_limit": 1000,
        }
    )
    with TestClient(create_app(configured)) as client:
        host = register(client, "Host")
        room = client.post(
            "/api/v1/rooms", json={"story_slug": "blackthorn_manor"}, headers=host
        ).json()
        response = client.post(
            f"/api/v1/rooms/{room['id']}/media-token", headers=host
        )
        assert response.status_code == 200, response.text
        body = response.json()
        claims = jwt.decode(
            body["token"], key.public_key(), algorithms=["RS256"], audience="jitsi"
        )
        assert claims["iss"] == "chat"
        assert claims["sub"] == "test-app"
        assert claims["room"] == room["id"]
        assert claims["context"]["user"]["moderator"] is True
        assert claims["context"]["features"]["recording"] is False
        assert claims["context"]["features"]["livestreaming"] is False
        assert claims["context"]["features"]["transcription"] is False
        assert body["domain"] == "8x8.vc"
        assert body["app_id"] == "test-app"


def test_media_token_denies_non_members(
    tmp_path: Path, settings: Settings, seeded: Path
) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "jaas-private.pem"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    configured = settings.model_copy(
        update={
            "enable_voice_video": True,
            "jaas_app_id": "test-app",
            "jaas_key_id": "test-key-id",
            "jaas_private_key_path": key_path,
            "register_rate_limit": 1000,
        }
    )
    with TestClient(create_app(configured)) as client:
        host = register(client, "Host")
        outsider = register(client, "Outsider")
        room = client.post(
            "/api/v1/rooms", json={"story_slug": "blackthorn_manor"}, headers=host
        ).json()
        response = client.post(
            f"/api/v1/rooms/{room['id']}/media-token", headers=outsider
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "NOT_A_MEMBER"
