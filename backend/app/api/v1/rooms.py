import uuid

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from backend.app.api.deps import CurrentUser, SessionDep
from backend.app.models import Room, RoomMember, Story, User
from backend.app.models.room import PRESENT_STATUSES
from backend.app.schemas.room import (
    CreatedRoomOut,
    CreateRoomIn,
    JoinRoomIn,
    ReadyIn,
    RoomOut,
    room_view,
)
from backend.app.services import rooms as svc

router = APIRouter(prefix="/rooms", tags=["rooms"])


async def _view(session: SessionDep, room: Room, viewer: User) -> RoomOut:
    story = await session.get(Story, room.story_id)
    rows = await session.execute(
        select(RoomMember, User.display_name)
        .join(User, User.id == RoomMember.user_id)
        .where(RoomMember.room_id == room.id, RoomMember.status.in_(PRESENT_STATUSES))
        .order_by(RoomMember.joined_at, RoomMember.id)
    )
    return room_view(room, story, [(m, name) for m, name in rows.all()], viewer.id)


@router.post("", status_code=201)
async def create(body: CreateRoomIn, user: CurrentUser, session: SessionDep) -> CreatedRoomOut:
    room, code = await svc.create_room(session, user, body.story_slug)
    view = await _view(session, room, user)
    return CreatedRoomOut(**view.model_dump(), invite_code=code)


@router.post("/join")
async def join(
    request: Request, body: JoinRoomIn, user: CurrentUser, session: SessionDep
) -> RoomOut:
    request.app.state.limits["join"].check(str(user.id))
    room = await svc.join_room(session, user, body.code)
    return await _view(session, room, user)


@router.get("/{room_id}")
async def read(room_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> RoomOut:
    return await _view(session, await svc.get_room_for(session, user, room_id), user)


@router.post("/{room_id}/ready")
async def ready(
    room_id: uuid.UUID, body: ReadyIn, user: CurrentUser, session: SessionDep
) -> RoomOut:
    return await _view(session, await svc.set_ready(session, user, room_id, body.ready), user)


@router.post("/{room_id}/start")
async def start(room_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> RoomOut:
    return await _view(session, await svc.start_room(session, user, room_id), user)


@router.post("/{room_id}/leave", status_code=204)
async def leave(room_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    await svc.leave_room(session, user, room_id)
    return Response(status_code=204)
