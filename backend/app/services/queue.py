"""Matchmaking queue (in-process, like the rate limiters). A group forms when 3+ compatible
people wait for the playable story; the room is created for them and they join it as usual."""

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import AppError
from backend.app.models import Profile, Story, User
from backend.app.services import matching, rooms

SUGGEST_AFTER_S = 90  # then offer an invite code or (demo) companions


@dataclass
class Entry:
    candidate: matching.Candidate
    joined_at: float = field(default_factory=time.monotonic)
    room_id: uuid.UUID | None = None
    explanations: list[str] = field(default_factory=list)


class Queue:
    def __init__(self) -> None:
        self.entries: dict[str, Entry] = {}
        self.lock = asyncio.Lock()


def _candidate(user: User, profile: Profile) -> matching.Candidate:
    return matching.Candidate(
        user_id=str(user.id),
        interests=frozenset(profile.interests),
        prefs=frozenset(profile.genres) | frozenset(profile.activities),
        availability=frozenset(profile.availability),
        roles=frozenset(profile.preferred_roles),
        shares_profile=profile.visibility == "match_only",
    )


async def blocked_pairs(session: AsyncSession, user_ids: list[str]) -> set[frozenset[str]]:
    """Pairs that must never be grouped. Blocks are stored from P16 on."""
    return set()


async def join(app: FastAPI, session: AsyncSession, user: User) -> Entry:
    profile = await session.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None:
        raise AppError(409, "PROFILE_REQUIRED", "Set up your profile first.")
    queue: Queue = app.state.queue
    async with queue.lock:
        entry = queue.entries.get(str(user.id))
        if entry is None or entry.room_id is not None:
            entry = queue.entries[str(user.id)] = Entry(_candidate(user, profile))
        await _try_form(queue, session)
        return entry


async def _try_form(queue: Queue, session: AsyncSession) -> None:
    while True:
        waiting = sorted(
            (e for e in queue.entries.values() if e.room_id is None), key=lambda e: e.joined_at
        )
        if len(waiting) < matching.GROUP_MIN:
            return
        ids = [e.candidate.user_id for e in waiting]
        group = matching.form_group(
            [e.candidate for e in waiting], await blocked_pairs(session, ids)
        )
        if group is None:
            return
        story = await session.scalar(
            select(Story).where(Story.playable.is_(True)).order_by(Story.title)
        )
        users = [await session.get(User, uuid.UUID(c.user_id)) for c in group]
        room, code = await rooms.create_room(session, users[0], story.slug)
        for user in users[1:]:
            await rooms.join_room(session, user, code)
        for candidate in group:
            entry = queue.entries[candidate.user_id]
            entry.room_id = room.id
            entry.explanations = matching.explain(candidate, group)


async def leave(app: FastAPI, user: User) -> None:
    queue: Queue = app.state.queue
    async with queue.lock:
        queue.entries.pop(str(user.id), None)


def status(app: FastAPI, user: User) -> dict:
    entry = app.state.queue.entries.get(str(user.id))
    if entry is None:
        return {"state": "idle"}
    waited = int(time.monotonic() - entry.joined_at)
    if entry.room_id is not None:
        return {
            "state": "matched",
            "room_id": str(entry.room_id),
            "explanations": entry.explanations,
        }
    return {
        "state": "waiting",
        "waited_s": waited,
        "suggest_alternatives": waited >= SUGGEST_AFTER_S,
    }
