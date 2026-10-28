"""The JaaS payload is room-scoped, short-lived and never records."""

import uuid

from backend.app.core.config import Settings
from backend.app.services.media import FEATURES_OFF, TOKEN_TTL_S, build_claims


def claims(moderator: bool = False) -> dict:
    return build_claims(
        "vpaas-magic-cookie-x",
        room_id=uuid.UUID(int=7),
        user_id=uuid.UUID(int=9),
        display_name="Ada",
        moderator=moderator,
        now=1_000,
    )


def test_room_scoped_and_short_lived() -> None:
    c = claims()
    assert (c["aud"], c["iss"], c["sub"]) == ("jitsi", "chat", "vpaas-magic-cookie-x")
    assert c["room"] == str(uuid.UUID(int=7)) and c["room"] != "*"
    assert c["context"]["room"] == {"regex": False}
    assert c["nbf"] <= c["iat"] == 1_000
    assert c["exp"] == 1_000 + TOKEN_TTL_S <= 1_000 + 2 * 60 * 60


def test_moderator_flag_is_a_string() -> None:
    assert claims(moderator=True)["context"]["user"]["moderator"] == "true"
    assert claims()["context"]["user"]["moderator"] == "false"


def test_recording_and_streaming_off() -> None:
    features = claims()["context"]["features"]
    assert set(features) == set(FEATURES_OFF)
    assert {"recording", "livestreaming", "transcription"} <= set(features)
    assert set(features.values()) == {"false"}


def test_media_enabled_needs_flag_and_credentials() -> None:
    base = Settings(_env_file=None, secret_key="x" * 32, app_env="test")
    full = {"jaas_app_id": "a", "jaas_key_id": "k", "jaas_private_key_path": "k.pem"}
    assert not base.model_copy(update=full).media_enabled
    assert base.model_copy(update={**full, "enable_voice_video": True}).media_enabled
    assert not base.model_copy(
        update={**full, "enable_voice_video": True, "jaas_key_id": ""}
    ).media_enabled
