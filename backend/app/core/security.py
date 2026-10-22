"""Password hashing (Argon2), access tokens (HS256 JWT) and token revocation."""

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

JWT_ALGORITHM = "HS256"

_hasher = PasswordHash((Argon2Hasher(),))
_dummy_hash: str | None = None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish time: with no stored hash, still pays for one verification."""
    global _dummy_hash
    if password_hash is None:
        _dummy_hash = _dummy_hash or _hasher.hash(uuid.uuid4().hex)
        _hasher.verify(password, _dummy_hash)
        return False
    return _hasher.verify(password, password_hash)


@dataclass(frozen=True)
class AccessToken:
    token: str
    jti: str
    expires_at: datetime


@dataclass(frozen=True)
class TokenClaims:
    sub: str
    jti: str
    exp: int


class InvalidToken(Exception):
    pass


def create_access_token(user_id: uuid.UUID, secret: str, minutes: int) -> AccessToken:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=minutes)
    jti = uuid.uuid4().hex
    claims = {"sub": str(user_id), "jti": jti, "iat": now, "exp": expires_at}
    return AccessToken(jwt.encode(claims, secret, algorithm=JWT_ALGORITHM), jti, expires_at)


def decode_access_token(token: str, secret: str) -> TokenClaims:
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "jti", "iat", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidToken from exc
    return TokenClaims(sub=claims["sub"], jti=claims["jti"], exp=claims["exp"])


class TokenDenylist:
    """Revoked token ids, kept only until the token would expire anyway (in-memory, MVP)."""

    def __init__(self) -> None:
        self._revoked: dict[str, int] = {}

    def revoke(self, jti: str, exp: int) -> None:
        self._prune()
        self._revoked[jti] = exp

    def is_revoked(self, jti: str) -> bool:
        return jti in self._revoked

    def _prune(self) -> None:
        now = int(time.time())
        self._revoked = {j: e for j, e in self._revoked.items() if e > now}
