"""Room chat: idempotent saves (dedupe on member + client id) and recent history."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import Message, RoomMember, User

HISTORY_LIMIT = 50


async def save_message(
    session: AsyncSession, member: RoomMember, body: str, client_message_id: str
) -> tuple[Message, bool]:
    """Returns (message, created). A retried client id returns the original message."""

    async def existing() -> Message | None:
        return await session.scalar(
            select(Message).where(
                Message.member_id == member.id, Message.client_message_id == client_message_id
            )
        )

    found = await existing()
    if found is not None:
        return found, False
    message = Message(
        room_id=member.room_id, member_id=member.id, body=body, client_message_id=client_message_id
    )
    session.add(message)
    try:
        await session.commit()
    except IntegrityError:  # the same send raced in from another tab
        await session.rollback()
        return await existing(), False
    return message, True


async def recent_messages(
    session: AsyncSession, room_id: uuid.UUID, limit: int = HISTORY_LIMIT
) -> list[tuple[Message, str | None]]:
    """Latest visible messages, oldest first, with the sender's display name."""
    rows = await session.execute(
        select(Message, User.display_name)
        .outerjoin(RoomMember, RoomMember.id == Message.member_id)
        .outerjoin(User, User.id == RoomMember.user_id)
        .where(Message.room_id == room_id, Message.moderation == "allowed")
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    return list(reversed(rows.all()))


def message_out(message: Message, display_name: str | None) -> dict:
    return {
        "id": str(message.id),
        "member_id": str(message.member_id) if message.member_id else None,
        "display_name": display_name,
        "type": message.type,
        "body": message.body,
        "client_message_id": message.client_message_id,
        "created_at": message.created_at.isoformat(),
    }
