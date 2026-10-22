import time
import uuid

import jwt
import pytest
from pydantic import ValidationError

from backend.app.core.config import PLACEHOLDER_SECRET, Settings
from backend.app.core.errors import AppError
from backend.app.core.ratelimit import RateLimiter
from backend.app.core.security import (
    InvalidToken,
    TokenDenylist,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

SECRET = "s" * 48


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery")
    assert hashed.startswith("$argon2id$")
    assert verify_password("correct horse battery", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("anything", None)


def test_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, SECRET, minutes=60)
    claims = decode_access_token(token.token, SECRET)
    assert claims.sub == str(user_id)
    assert claims.jti == token.jti
    raw = jwt.decode(token.token, SECRET, algorithms=["HS256"])
    assert set(raw) == {"sub", "jti", "iat", "exp"}
    assert raw["exp"] - raw["iat"] == 3600


@pytest.mark.parametrize(
    "token",
    [
        lambda: create_access_token(uuid.uuid4(), SECRET, minutes=-1).token,  # expired
        lambda: create_access_token(uuid.uuid4(), "t" * 48, minutes=5).token,  # wrong key
        lambda: jwt.encode({"sub": "x", "jti": "y", "iat": 0, "exp": 2**40}, None, "none"),
        lambda: jwt.encode({"sub": "x", "exp": 2**40}, SECRET, "HS256"),  # missing jti/iat
        lambda: "garbage",
    ],
)
def test_bad_tokens_rejected(token) -> None:
    with pytest.raises(InvalidToken):
        decode_access_token(token(), SECRET)


def test_denylist_prunes_expired_entries() -> None:
    denylist = TokenDenylist()
    denylist.revoke("old", exp=int(time.time()) - 10)
    denylist.revoke("live", exp=int(time.time()) + 600)
    assert denylist.is_revoked("live")
    assert not denylist.is_revoked("old")


def test_rate_limiter_sliding_window() -> None:
    now = [0.0]
    limiter = RateLimiter(limit=2, window_s=10, clock=lambda: now[0])
    assert limiter.hit("k") is None
    assert limiter.hit("k") is None
    assert limiter.hit("k") == pytest.approx(10)
    assert limiter.hit("other") is None
    now[0] = 10.0  # both earlier hits have left the window
    assert limiter.hit("k") is None
    now[0] = 12.5
    limiter.check("k")
    with pytest.raises(AppError) as exc:
        limiter.check("k")
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "8"  # oldest hit (t=10) frees at t=20


def test_settings_reject_short_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, secret_key="too-short")


def test_settings_reject_placeholder_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", secret_key=PLACEHOLDER_SECRET)
    assert Settings(_env_file=None, app_env="development", secret_key=PLACEHOLDER_SECRET)
