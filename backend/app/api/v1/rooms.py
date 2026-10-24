import uuid

from fastapi import APIRouter, Request, Response

from backend.app.api.deps import CurrentUser, SessionDep
from backend.app.models import Room, Story, User
from backend.app.schemas.room import (
    CreatedRoomOut,
    CreateRoomIn,
    JoinRoomIn,
    ReadyIn,
    RoomOut,
    room_view,
)
from backend.app.services import rooms as svc
from backend.app.ws.notify import notify_room

router = APIRouter(prefix="/rooms", tags=["rooms"])


async def _view(session: SessionDep, room: Room, viewer: User) -> RoomOut:
    story = await session.get(Story, room.story_id)
    return room_view(room, story, await svc.members_with_names(session, room), viewer.id)


async def _notify(
    request: Request, session: SessionDep, room: Room, user: User, event: str
) -> None:
    """Pushes the change to everyone connected over WebSocket."""
    member = await svc.member_of(session, room.id, user.id)
    await notify_room(request.app, room.id, event, member.id)


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
    await _notify(request, session, room, user, "joined")
    return await _view(session, room, user)


@router.get("/{room_id}")
async def read(room_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> RoomOut:
    return await _view(session, await svc.get_room_for(session, user, room_id), user)


@router.post("/{room_id}/ready")
async def ready(
    request: Request, room_id: uuid.UUID, body: ReadyIn, user: CurrentUser, session: SessionDep
) -> RoomOut:
    room = await svc.set_ready(session, user, room_id, body.ready)
    await _notify(request, session, room, user, "ready" if body.ready else "unready")
    return await _view(session, room, user)


@router.post("/{room_id}/start")
async def start(
    request: Request, room_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> RoomOut:
    room = await svc.start_room(session, user, room_id)
    await _notify(request, session, room, user, "started")
    return await _view(session, room, user)


@router.post("/{room_id}/leave", status_code=204)
async def leave(
    request: Request, room_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    await svc.leave_room(session, user, room_id)
    member = await svc.member_of(session, room_id, user.id)
    await notify_room(request.app, room_id, "left", member.id)
    await request.app.state.ws.close_member(room_id, member.id, 1000)
    return Response(status_code=204)
