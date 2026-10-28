"""Create three labelled demo accounts with profiles and a waiting room for the playable case.

    uv run python scripts/demo.py

Safe to run repeatedly: existing demo accounts get a fresh password and a new room.
Refuses to run when APP_ENV=production. Run scripts/seed.py first.
"""

import asyncio
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from backend.app.content import profile_options as opts  # noqa: E402
from backend.app.core.config import get_settings  # noqa: E402
from backend.app.core.security import hash_password  # noqa: E402
from backend.app.db.session import create_engine, create_sessionmaker  # noqa: E402
from backend.app.models import Story, User  # noqa: E402
from backend.app.schemas.auth import RegisterIn  # noqa: E402
from backend.app.schemas.profile import ProfileIn  # noqa: E402
from backend.app.services import auth, profiles, rooms  # noqa: E402

DEMO_PEOPLE = ("Ada", "Bo", "Cy")
STORY = "blackthorn_manor"


def _ids(options, *indexes: int) -> list[str]:
    return [options[i][0] for i in indexes]


def _profile(n: int) -> ProfileIn:
    """Overlapping but different interests, so matching has something to explain."""
    return ProfileIn(
        interests=_ids(opts.INTERESTS, 0, 5, 6 + n),
        genres=_ids(opts.GENRES, 0),
        availability=_ids(opts.AVAILABILITY, 0, n),
        interaction_style=("thoughtful", "playful", "analytical")[n],
        preferred_roles=_ids(opts.ROLES, n),
        visibility="match_only",
        shareable_summary="Demo account for trying ECHO.",
    )


async def _demo_user(session, name: str, password: str) -> User:
    email = f"demo-{name.lower()}@example.com"
    user = await session.scalar(select(User).where(User.email_normalized == email))
    if user is None:
        data = RegisterIn(
            email=email, password=password, display_name=f"{name} - demo", age_confirmed=True
        )
        user = await auth.register_user(session, data)
    else:
        user.password_hash = await asyncio.to_thread(hash_password, password)
        await session.commit()
    return user


async def main() -> None:
    settings = get_settings()
    if settings.app_env == "production":
        sys.exit("demo.py refuses to run with APP_ENV=production")
    password = secrets.token_urlsafe(12)
    engine = create_engine(settings.database_url)
    try:
        async with create_sessionmaker(engine)() as session:
            if await session.scalar(select(Story.id).where(Story.slug == STORY)) is None:
                sys.exit("No stories yet: run `uv run python scripts/seed.py` first.")
            people = []
            for n, name in enumerate(DEMO_PEOPLE):
                user = await _demo_user(session, name, password)
                await profiles.upsert_profile(session, user, _profile(n))
                people.append(user)
            room, code = await rooms.create_room(session, people[0], STORY)
            for guest in people[1:]:
                await rooms.join_room(session, guest, code)
    finally:
        await engine.dispose()

    print("Demo accounts (password for all three, shown once):", password)
    for user in people:
        print(f"  {user.display_name:<12} {user.email_normalized}")
    print(f"Waiting room for {STORY}: code {code[:4]}-{code[4:]} (Ada hosts; Bo and Cy joined)")
    print(f"Sign in to each account in its own browser tab and open /room.html?id={room.id}")


if __name__ == "__main__":
    asyncio.run(main())
