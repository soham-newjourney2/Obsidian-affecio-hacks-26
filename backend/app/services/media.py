"""Optional voice/video: room-scoped JaaS (8x8 Jitsi as a Service) tokens.

The RS256 private key stays on the server; the browser only ever receives the signed token.
Claim format per the 8x8 JaaS JWT docs: aud "jitsi", iss "chat", sub = AppID, kid header,
and string "true"/"false" values for the moderator flag and features.
"""

import asyncio
import time
import uuid
from pathlib import Path

import jwt

from backend.app.core.config import Settings
from backend.app.core.errors import AppError

DOMAIN = "8x8.vc"
TOKEN_TTL_S = 2 * 60 * 60  # At most 2 h
NBF_SKEW_S = 10  # tolerate small clock drift between us and 8x8
# Everything that would record or leave the call is off; joining is always optional.
FEATURES_OFF = (
    "recording",
    "livestreaming",
    "transcription",
    "inbound-call",
    "outbound-call",
    "sip-inbound-call",
    "sip-outbound-call",
)


def _unavailable() -> AppError:
    return AppError(503, "MEDIA_UNAVAILABLE", "Voice/video is not configured.")


def build_claims(
    app_id: str,
    *,
    room_id: uuid.UUID,
    user_id: uuid.UUID,
    display_name: str,
    moderator: bool,
    now: int,
) -> dict:
    """The JaaS payload for one member of one room (pure, for tests)."""
    return {
        "aud": "jitsi",
        "iss": "chat",
        "sub": app_id,
        "room": str(room_id),  # this room only, never "*"
        "iat": now,
        "nbf": now - NBF_SKEW_S,
        "exp": now + TOKEN_TTL_S,
        "context": {
            "user": {
                "id": str(user_id),
                "name": display_name,
                "moderator": "true" if moderator else "false",
            },
            "features": {name: "false" for name in FEATURES_OFF},
            "room": {"regex": False},
        },
    }


async def media_token(
    settings: Settings,
    *,
    room_id: uuid.UUID,
    user_id: uuid.UUID,
    display_name: str,
    moderator: bool,
) -> dict[str, str]:
    """Sign a token for a room member (membership is checked by the caller)."""
    if not settings.media_enabled:
        raise _unavailable()
    try:
        private_key = await asyncio.to_thread(
            Path(settings.jaas_private_key_path).read_text, encoding="utf-8"
        )
    except (OSError, UnicodeError):
        raise _unavailable() from None
    claims = build_claims(
        settings.jaas_app_id,
        room_id=room_id,
        user_id=user_id,
        display_name=display_name,
        moderator=moderator,
        now=int(time.time()),
    )
    try:
        token = jwt.encode(
            claims,
            private_key,
            algorithm="RS256",
            headers={"kid": settings.jaas_key_id, "typ": "JWT"},
        )
    except (ValueError, TypeError, NotImplementedError):
        raise _unavailable() from None
    return {"token": token, "room": str(room_id), "app_id": settings.jaas_app_id, "domain": DOMAIN}
