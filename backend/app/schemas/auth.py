import re
import uuid
from datetime import datetime
from typing import Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator

_DISPLAY_NAME = re.compile(r"^[\w][\w .'\-]*$")


def normalize_email(raw: str) -> str:
    """Canonical form used for storage and lookup. Raises ValueError if not an email."""
    try:
        return validate_email(raw.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError("invalid email address") from exc


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=128)
    display_name: str
    age_confirmed: bool

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not 2 <= len(v) <= 24 or not _DISPLAY_NAME.match(v):
            raise ValueError("display name must be 2–24 letters, numbers, spaces or . ' - _")
        return v

    @field_validator("age_confirmed")
    @classmethod
    def _adult(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("you must confirm you are 18 or older")
        return v


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str = Field(validation_alias="email_normalized")
    display_name: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 (OAuth token type, not a secret)
    expires_in: int
    user: UserOut
