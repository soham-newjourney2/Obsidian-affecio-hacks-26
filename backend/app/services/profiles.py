from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import Profile, User
from backend.app.schemas.profile import ProfileIn


async def get_profile(session: AsyncSession, user: User) -> Profile | None:
    return await session.scalar(select(Profile).where(Profile.user_id == user.id))


async def upsert_profile(session: AsyncSession, user: User, data: ProfileIn) -> Profile:
    values = data.model_dump()
    profile = await get_profile(session, user)
    if profile is None:
        session.add(Profile(user_id=user.id, **values))
        try:
            await session.commit()
        except IntegrityError:
            # Another tab created it first: fall through and apply as an update.
            await session.rollback()
            profile = await get_profile(session, user)
            if profile is None:
                raise
    if profile is not None:
        for field, value in values.items():
            setattr(profile, field, value)
        await session.commit()
    return await get_profile(session, user)
