"""WebSocket envelopes (§7).

Client frames are {type, id, payload}; server frames are {type, id, ts, room_id, payload}.
"""

import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models.message import MAX_BODY

MAX_FRAME_BYTES = 8 * 1024


class ClientFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(max_length=40)
    id: str | None = Field(default=None, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class AuthIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(max_length=4096)


class ChatSendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_message_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    body: str = Field(max_length=MAX_BODY * 2)

    @field_validator("body")
    @classmethod
    def _clean(cls, v: str) -> str:
        # Keep line breaks, drop other control characters, trim, cap blank runs.
        v = "".join(ch for ch in v if ch == "\n" or not unicodedata.category(ch).startswith("C"))
        v = re.sub(r"\n{3,}", "\n\n", v).strip()
        if not 1 <= len(v) <= MAX_BODY:
            raise ValueError(f"message must be 1–{MAX_BODY} characters")
        return v


class ReadyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool = True


def envelope(type_: str, room_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": type_,
        "id": uuid.uuid4().hex,
        "ts": datetime.now(UTC).isoformat(),
        "room_id": str(room_id),
        "payload": payload,
    }


def error(room_id: uuid.UUID, code: str, ref_id: str | None = None) -> dict[str, Any]:
    return envelope("error", room_id, {"code": code, "ref_id": ref_id})
