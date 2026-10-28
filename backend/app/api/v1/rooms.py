import uuid

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.deps import CurrentUser, SessionDep
from backend.app.core.errors import AppError
from backend.app.models import Room, Story, User
from backend.app.schemas.room import (
    CreatedRoomOut,
    CreateRoomIn,
    JoinRoomIn,
    ReadyIn,
    RoomOut,
    room_view,
)
from backend.app.services import companions, media
from backend.app.services import game as game_service
from backend.app.services import rooms as svc
from backend.app.ws.notify import deliver_game, notify_room

router = APIRouter(prefix="/rooms", tags=["rooms"])


async def _view(request: Request, session: SessionDep, room: Room, viewer: User) -> RoomOut:
    story = await session.get(Story, room.story_id)
    game = await game_service.session_for_room(session, room.id)
    members = await svc.members_with_names(session, room)
    return room_view(
        room,
        story,
        members,
        viewer.id,
        session_id=game.id if game else None,
        settings=request.app.state.settings,
    )


def _demo(request: Request) -> bool:
    return request.app.state.settings.demo_mode


async def _notify(
    request: Request, session: SessionDep, room: Room, user: User, event: str
) -> None:
    """Pushes the change to everyone connected over WebSocket."""
    member = await svc.member_of(session, room.id, user.id)
    await notify_room(request.app, room.id, event, member.id)


@router.post("", status_code=201)
async def create(
    request: Request, body: CreateRoomIn, user: CurrentUser, session: SessionDep
) -> CreatedRoomOut:
    room, code = await svc.create_room(session, user, body.story_slug)
    view = await _view(request, session, room, user)
    return CreatedRoomOut(**view.model_dump(), invite_code=code)


@router.post("/join")
async def join(
    request: Request, body: JoinRoomIn, user: CurrentUser, session: SessionDep
) -> RoomOut:
    request.app.state.limits["join"].check(str(user.id))
    room = await svc.join_room(session, user, body.code)
    await _notify(request, session, room, user, "joined")
    return await _view(request, session, room, user)


@router.get("/{room_id}")
async def read(
    request: Request, room_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> RoomOut:
    room = await svc.get_room_for(session, user, room_id)
    return await _view(request, session, room, user)


@router.post("/{room_id}/ready")
async def ready(
    request: Request, room_id: uuid.UUID, body: ReadyIn, user: CurrentUser, session: SessionDep
) -> RoomOut:
    room = await svc.set_ready(session, user, room_id, body.ready)
    await _notify(request, session, room, user, "ready" if body.ready else "unready")
    return await _view(request, session, room, user)


@router.post("/{room_id}/start")
async def start(
    request: Request, room_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> RoomOut:
    room = await svc.start_room(session, user, room_id)
    started = await game_service.start_game(request.app, room.id)
    await _notify(request, session, room, user, "started")  # room view now carries session_id
    await deliver_game(request.app, started)
    return await _view(request, session, room, user)


class CompanionsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=1, le=3)


@router.post("/{room_id}/media-token")
async def media_token(
    request: Request, room_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    """A short-lived JaaS token for a present member; the host joins as moderator."""
    settings = request.app.state.settings
    if not settings.enable_voice_video:
        raise AppError(404, "NOT_FOUND", "Not Found")
    room = await svc.get_room_for(session, user, room_id)  # 404 unknown, 403 not a present member
    return await media.media_token(
        settings,
        room_id=room.id,
        user_id=user.id,
        display_name=user.display_name,
        moderator=room.host_user_id == user.id,
    )


@router.post("/{room_id}/companions")
async def add_companions(
    request: Request, room_id: uuid.UUID, body: CompanionsIn, user: CurrentUser, session: SessionDep
) -> RoomOut:
    """Demo only (D12): the host fills empty seats with labelled AI companions."""
    if not _demo(request):
        raise AppError(404, "NOT_FOUND", "Not Found")
    room, first = await companions.add_companions(session, user, room_id, body.count)
    await notify_room(request.app, room.id, "joined", first)
    return await _view(request, session, room, user)


@router.post("/{room_id}/leave", status_code=204)
async def leave(
    request: Request, room_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    await svc.leave_room(session, user, room_id)
    member = await svc.member_of(session, room_id, user.id)
    freed = await game_service.leave_game(request.app, room_id, member.id)
    if freed:
        await deliver_game(request.app, freed)
    await notify_room(request.app, room_id, "left", member.id)
    await request.app.state.ws.close_member(room_id, member.id, 1000)
    return Response(status_code=204)
