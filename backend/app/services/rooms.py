"""Rooms: create, join by invite code, ready, leave, start.

Every mutation starts with `_lock_room`, a no-op UPDATE on the room row. On SQLite that takes the
database write lock before anything is read (other writers wait on busy_timeout); on Postgres it
takes a row lock. Capacity and start preconditions are therefore checked and applied atomically.
"""

import hashlib
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import AppError
from backend.app.db.base import utcnow
from backend.app.models import Room, RoomMember, Story, User
from backend.app.models.room import PRESENT_STATUSES

INVITE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"  # RFC 4648 base32
INVITE_LENGTH = 8
INVITE_TTL = timedelta(hours=2)
# Characters people type by mistake for base32 letters.
_CONFUSABLES = str.maketrans({"0": "O", "1": "I", "8": "B"})


def new_invite_code() -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_LENGTH))


def normalize_invite_code(raw: str) -> str:
    return "".join(ch for ch in raw.upper() if ch.isalnum()).translate(_CONFUSABLES)


def hash_invite_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _error(status: int, code: str, message: str) -> AppError:
    return AppError(status, code, message)


def invite_invalid() -> AppError:
    # One answer for unknown, expired and revoked codes: no oracle for guessing.
    return _error(404, "INVITE_INVALID", "This invite code is invalid or has expired.")


def not_a_member() -> AppError:
    return _error(403, "NOT_A_MEMBER", "You are not in this room.")


async def _lock_room(session: AsyncSession, **where) -> Room | None:
    conditions = [getattr(Room, key) == value for key, value in where.items()]
    room_id = await session.scalar(
        update(Room).where(*conditions).values(status=Room.status).returning(Room.id)
    )
    if room_id is None:
        return None
    return await session.get(Room, room_id, populate_existing=True)


async def present_members(session: AsyncSession, room: Room) -> list[RoomMember]:
    result = await session.scalars(
        select(RoomMember)
        .where(RoomMember.room_id == room.id, RoomMember.status.in_(PRESENT_STATUSES))
        .order_by(RoomMember.joined_at, RoomMember.id)
    )
    return list(result)


async def _membership(session: AsyncSession, room: Room, user: User) -> RoomMember | None:
    return await session.scalar(
        select(RoomMember).where(RoomMember.room_id == room.id, RoomMember.user_id == user.id)
    )


async def _require_present(session: AsyncSession, room: Room, user: User) -> RoomMember:
    member = await _membership(session, room, user)
    if member is None or member.status not in PRESENT_STATUSES:
        raise not_a_member()
    return member


async def create_room(session: AsyncSession, user: User, story_slug: str) -> tuple[Room, str]:
    story = await session.scalar(
        select(Story).where(Story.slug == story_slug, Story.rights_status != "excluded")
    )
    if story is None:
        raise _error(404, "STORY_NOT_FOUND", "Story not found.")
    if not story.playable:
        raise _error(409, "STORY_NOT_PLAYABLE", "This case is not open yet.")
    code = new_invite_code()
    now = utcnow()
    room = Room(
        invite_hash=hash_invite_code(code),
        host_user_id=user.id,
        story_id=story.id,
        story_version=story.version,
        created_at=now,
        expires_at=now + INVITE_TTL,
    )
    session.add(room)
    await session.flush()
    session.add(RoomMember(room_id=room.id, user_id=user.id, joined_at=now))
    await session.commit()
    return room, code


async def join_room(session: AsyncSession, user: User, raw_code: str) -> Room:
    room = await _lock_room(session, invite_hash=hash_invite_code(normalize_invite_code(raw_code)))
    if room is None or room.status != "waiting" or room.expires_at <= utcnow():
        await session.rollback()
        raise invite_invalid()
    member = await _membership(session, room, user)
    if member is not None and member.status in PRESENT_STATUSES:
        # Already in: a no-op. Commit (not rollback) releases the lock and keeps `room` loaded.
        await session.commit()
        return room
    if member is not None and member.status == "removed":
        await session.rollback()
        raise _error(403, "REMOVED", "You can't rejoin this room.")
    story = await session.get(Story, room.story_id)
    if len(await present_members(session, room)) >= story.max_players:
        await session.rollback()
        raise _error(409, "ROOM_FULL", "This room is full.")
    if member is None:
        session.add(RoomMember(room_id=room.id, user_id=user.id))
    else:  # rejoining after leaving
        member.status, member.left_at, member.joined_at = "joined", None, utcnow()
    await session.commit()
    return room


async def get_room_for(session: AsyncSession, user: User, room_id: uuid.UUID) -> Room:
    room = await session.get(Room, room_id)
    if room is None:
        raise _error(404, "ROOM_NOT_FOUND", "Room not found.")
    await _require_present(session, room, user)
    return room


async def _locked_room(session: AsyncSession, room_id: uuid.UUID) -> Room:
    room = await _lock_room(session, id=room_id)
    if room is None:
        await session.rollback()
        raise _error(404, "ROOM_NOT_FOUND", "Room not found.")
    return room


async def set_ready(session: AsyncSession, user: User, room_id: uuid.UUID, ready: bool) -> Room:
    room = await _locked_room(session, room_id)
    try:
        member = await _require_present(session, room, user)
        if room.status != "waiting":
            raise _error(409, "ROOM_NOT_WAITING", "This case has already begun.")
    except AppError:
        await session.rollback()
        raise
    member.status = "ready" if ready else "joined"
    await session.commit()
    return room


async def leave_room(session: AsyncSession, user: User, room_id: uuid.UUID) -> None:
    room = await _locked_room(session, room_id)
    try:
        member = await _require_present(session, room, user)
    except AppError:
        await session.rollback()
        raise
    member.status, member.left_at = "left", utcnow()
    await session.flush()
    remaining = [m for m in await present_members(session, room) if m.user_id is not None]
    if not remaining:
        if room.status in ("waiting", "active"):
            room.status, room.ended_at, room.invite_hash = "abandoned", utcnow(), None
    elif room.host_user_id == user.id:
        room.host_user_id = remaining[0].user_id  # longest-present member becomes host
    await session.commit()


async def start_room(session: AsyncSession, user: User, room_id: uuid.UUID) -> Room:
    room = await _locked_room(session, room_id)
    try:
        await _require_present(session, room, user)
        if room.host_user_id != user.id:
            raise _error(403, "NOT_HOST", "Only the host can start the case.")
        if room.status != "waiting":
            raise _error(409, "ROOM_NOT_WAITING", "This case has already begun.")
        story = await session.get(Story, room.story_id)
        members = await present_members(session, room)
        if not story.min_players <= len(members) <= story.max_players:
            raise _error(
                409,
                "NOT_ENOUGH_PLAYERS",
                f"A case needs {story.min_players}–{story.max_players} players.",
            )
        if any(m.status != "ready" for m in members):
            raise _error(409, "NOT_ALL_READY", "Everyone needs to be ready first.")
    except AppError:
        await session.rollback()
        raise
    now = utcnow()
    room.status, room.started_at, room.invite_hash = "active", now, None
    for member in members:
        member.status = "playing"
    await session.commit()
    return room


async def members_with_names(session: AsyncSession, room: Room) -> list[tuple[RoomMember, str]]:
    """Present human members (seat order) with display names, for room views."""
    rows = await session.execute(
        select(RoomMember, User.display_name)
        .join(User, User.id == RoomMember.user_id)
        .where(RoomMember.room_id == room.id, RoomMember.status.in_(PRESENT_STATUSES))
        .order_by(RoomMember.joined_at, RoomMember.id)
    )
    return [(member, name) for member, name in rows.all()]


async def member_of(
    session: AsyncSession, room_id: uuid.UUID, user_id: uuid.UUID
) -> RoomMember | None:
    return await session.scalar(
        select(RoomMember).where(RoomMember.room_id == room_id, RoomMember.user_id == user_id)
    )
