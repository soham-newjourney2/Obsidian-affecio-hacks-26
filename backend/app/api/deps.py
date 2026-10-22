"""Shared request dependencies: DB session, client IP and the authenticated user."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import AppError
from backend.app.core.security import InvalidToken, TokenClaims, decode_access_token
from backend.app.models import User

_bearer = HTTPBearer(auto_error=False)


def unauthorized() -> AppError:
    return AppError(401, "UNAUTHORIZED", "Please sign in.", headers={"WWW-Authenticate": "Bearer"})


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@dataclass(frozen=True)
class AuthContext:
    user: User
    claims: TokenClaims


async def current_auth(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    if credentials is None:
        raise unauthorized()
    secret = request.app.state.settings.secret_key.get_secret_value()
    try:
        claims = decode_access_token(credentials.credentials, secret)
        user_id = uuid.UUID(claims.sub)
    except (InvalidToken, ValueError):
        raise unauthorized() from None
    if request.app.state.denylist.is_revoked(claims.jti):
        raise unauthorized()
    user = await session.get(User, user_id)
    if user is None or user.status != "active":
        raise unauthorized()
    return AuthContext(user=user, claims=claims)


async def current_user(auth: Annotated[AuthContext, Depends(current_auth)]) -> User:
    return auth.user


SessionDep = Annotated[AsyncSession, Depends(get_session)]
AuthDep = Annotated[AuthContext, Depends(current_auth)]
CurrentUser = Annotated[User, Depends(current_user)]
