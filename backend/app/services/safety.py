"""Connections (mutual opt-in), blocks and reports (P16).

- A connection needs two yeses, and only between human co-players of a finished case.
- A decline is never visible to the person who asked: their request just stays "requested".
- A block ends requests both ways, hides each from the other's lists and keeps them apart in
  matching. Connections show a display name and the shareable summary only.
"""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import AppError
from backend.app.models import (
    Block,
    ConnectionRequest,
    GameSession,
    Message,
    Profile,
    Report,
    RoomMember,
    User,
)


def unavailable() -> AppError:
    # One answer for "blocked", "not a co-player" and "unknown": nothing to probe.
    return AppError(409, "CONNECTION_UNAVAILABLE", "You can't connect with this person.")


async def is_blocked(session: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> bool:
    return bool(
        await session.scalar(
            select(Block.id).where(
                or_(
                    (Block.blocker == a) & (Block.blocked == b),
                    (Block.blocker == b) & (Block.blocked == a),
                )
            )
        )
    )


async def blocked_pairs(session: AsyncSession, user_ids: list[str]) -> set[frozenset[str]]:
    ids = [uuid.UUID(u) for u in user_ids]
    rows = await session.execute(
        select(Block.blocker, Block.blocked).where(Block.blocker.in_(ids), Block.blocked.in_(ids))
    )
    return {frozenset((str(a), str(b))) for a, b in rows.all()}


async def co_players(session: AsyncSession, game: GameSession) -> set[uuid.UUID]:
    """Humans who were seated in this case (companions have no user and never count)."""
    rows = await session.scalars(
        select(RoomMember.user_id).where(
            RoomMember.room_id == game.room_id,
            RoomMember.user_id.is_not(None),
            RoomMember.role.is_not(None),
        )
    )
    return set(rows)


async def request(
    session: AsyncSession, user: User, session_id: uuid.UUID, to_user: uuid.UUID
) -> str:
    """Returns "requested" or "connected" (when the other person had already asked)."""
    game = await session.get(GameSession, session_id)
    if game is None or game.status == "active" or to_user == user.id:
        raise unavailable()
    players = await co_players(session, game)
    if (
        user.id not in players
        or to_user not in players
        or await is_blocked(session, user.id, to_user)
    ):
        raise unavailable()
    reverse = await session.scalar(
        select(ConnectionRequest).where(
            ConnectionRequest.session_id == game.id,
            ConnectionRequest.from_user == to_user,
            ConnectionRequest.to_user == user.id,
        )
    )
    mine = await session.scalar(
        select(ConnectionRequest).where(
            ConnectionRequest.session_id == game.id,
            ConnectionRequest.from_user == user.id,
            ConnectionRequest.to_user == to_user,
        )
    )
    if mine is None:
        mine = ConnectionRequest(session_id=game.id, from_user=user.id, to_user=to_user)
        session.add(mine)
    if reverse is not None and reverse.status == "pending":  # both said yes
        reverse.status = mine.status = "accepted"
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
    return "connected" if mine.status == "accepted" else "requested"


async def respond(session: AsyncSession, user: User, request_id: uuid.UUID, accept: bool) -> None:
    req = await session.get(ConnectionRequest, request_id)
    if req is None or req.to_user != user.id or req.status != "pending":
        raise AppError(404, "REQUEST_NOT_FOUND", "Request not found.")
    if accept and await is_blocked(session, req.from_user, req.to_user):
        raise unavailable()
    req.status = "accepted" if accept else "declined"
    await session.commit()


async def overview(session: AsyncSession, user: User) -> dict:
    rows = list(
        await session.scalars(
            select(ConnectionRequest).where(
                or_(ConnectionRequest.from_user == user.id, ConnectionRequest.to_user == user.id)
            )
        )
    )
    blocked = {
        b
        for (a, b) in (
            await session.execute(
                select(Block.blocker, Block.blocked).where(
                    or_(Block.blocker == user.id, Block.blocked == user.id)
                )
            )
        ).all()
        for b in (a, b)
    } - {user.id}

    connected, incoming, outgoing = {}, [], {}
    for r in rows:
        other = r.to_user if r.from_user == user.id else r.from_user
        if other in blocked:
            continue
        if r.status == "accepted":
            connected[other] = True
        elif r.to_user == user.id and r.status == "pending":
            incoming.append(r)
        elif r.from_user == user.id and r.status in ("pending", "declined"):
            outgoing[other] = True  # a decline looks exactly like "still pending"

    async def person(user_id: uuid.UUID, with_summary: bool) -> dict:
        other = await session.get(User, user_id)
        out = {"user_id": str(user_id), "display_name": other.display_name}
        if with_summary:
            profile = await session.scalar(select(Profile).where(Profile.user_id == user_id))
            out["shareable_summary"] = profile.shareable_summary if profile else ""
        return out

    return {
        "connections": [await person(u, True) for u in connected],
        "incoming": [
            {"request_id": str(r.id), **(await person(r.from_user, False))}
            for r in incoming
            if r.from_user not in connected
        ],
        "outgoing": [await person(u, False) for u in outgoing if u not in connected],
    }


async def block(session: AsyncSession, user: User, target: uuid.UUID) -> None:
    if target == user.id or await session.get(User, target) is None:
        raise AppError(404, "USER_NOT_FOUND", "User not found.")
    if not await session.scalar(
        select(Block.id).where(Block.blocker == user.id, Block.blocked == target)
    ):
        session.add(Block(blocker=user.id, blocked=target))
    pending = await session.scalars(
        select(ConnectionRequest).where(
            ConnectionRequest.status == "pending",
            or_(
                (ConnectionRequest.from_user == user.id) & (ConnectionRequest.to_user == target),
                (ConnectionRequest.from_user == target) & (ConnectionRequest.to_user == user.id),
            ),
        )
    )
    for req in pending:
        req.status = "withdrawn"
    await session.commit()


async def report(session: AsyncSession, user: User, data: dict) -> Report:
    if data.get("message_id"):
        message = await session.get(Message, data["message_id"])
        if message is None:
            raise AppError(404, "MESSAGE_NOT_FOUND", "Message not found.")
        data.setdefault("room_id", message.room_id)
    row = Report(reporter=user.id, **data)
    session.add(row)
    await session.commit()
    return row
