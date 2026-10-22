"""Registration and credential checks. Argon2 work runs off the event loop."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from backend.app.core.errors import AppError
from backend.app.core.security import hash_password, verify_password
from backend.app.db.base import utcnow
from backend.app.models import User
from backend.app.schemas.auth import RegisterIn, normalize_email


def email_taken() -> AppError:
    return AppError(409, "EMAIL_TAKEN", "An account with this email already exists.")


async def register_user(session: AsyncSession, data: RegisterIn) -> User:
    if await session.scalar(select(User.id).where(User.email_normalized == data.email)):
        raise email_taken()
    user = User(
        email_normalized=data.email,
        password_hash=await run_in_threadpool(hash_password, data.password),
        display_name=data.display_name,
        age_confirmed=True,
        last_login_at=utcnow(),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:  # lost a race with a concurrent registration
        await session.rollback()
        raise email_taken() from None
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    """Returns the user only for correct credentials on an active account."""
    try:
        normalized = normalize_email(email)
    except ValueError:
        normalized = None
    user = None
    if normalized:
        user = await session.scalar(select(User).where(User.email_normalized == normalized))
    stored_hash = user.password_hash if user else None
    if not await run_in_threadpool(verify_password, password, stored_hash):
        return None
    if user is None or user.status != "active":
        return None
    user.last_login_at = utcnow()
    await session.commit()
    return user
