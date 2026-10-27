import time
import uuid
from pathlib import Path

import jwt

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
from backend.app.services import companions
from backend.app.services import game as game_service
from backend.app.services import rooms as svc
from backend.app.ws.notify import deliver_game, notify_room

router = APIRouter(prefix="/rooms", tags=["rooms"])


async def _view(session: SessionDep, room: Room, viewer: User, demo: bool = False) -> RoomOut:
    story = await session.get(Story, room.story_id)
    game = await game_service.session_for_room(session, room.id)
    members = await svc.members_with_names(session, room)
    return room_view(
        room, story, members, viewer.id, session_id=game.id if game else None, demo=demo
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
    view = await _view(session, room, user, _demo(request))
    return CreatedRoomOut(**view.model_dump(), invite_code=code)


@router.post("/join")
async def join(
    request: Request, body: JoinRoomIn, user: CurrentUser, session: SessionDep
) -> RoomOut:
    request.app.state.limits["join"].check(str(user.id))
    room = await svc.join_room(session, user, body.code)
    await _notify(request, session, room, user, "joined")
    return await _view(session, room, user, _demo(request))


@router.get("/{room_id}")
async def read(
    request: Request, room_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> RoomOut:
    room = await svc.get_room_for(session, user, room_id)
    return await _view(session, room, user, _demo(request))


@router.post("/{room_id}/ready")
async def ready(
    request: Request, room_id: uuid.UUID, body: ReadyIn, user: CurrentUser, session: SessionDep
) -> RoomOut:
    room = await svc.set_ready(session, user, room_id, body.ready)
    await _notify(request, session, room, user, "ready" if body.ready else "unready")
    return await _view(session, room, user, _demo(request))


@router.post("/{room_id}/start")
async def start(
    request: Request, room_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> RoomOut:
    room = await svc.start_room(session, user, room_id)
    started = await game_service.start_game(request.app, room.id)
    await _notify(request, session, room, user, "started")  # room view now carries session_id
    await deliver_game(request.app, started)
    return await _view(session, room, user, _demo(request))


class CompanionsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=1, le=3)


@router.post("/{room_id}/media-token")
async def media_token(
    request: Request, room_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    """Issue a short-lived, room-scoped JaaS token to a current room member."""
    settings = request.app.state.settings
    if not settings.enable_voice_video:
        raise AppError(404, "MEDIA_DISABLED", "Voice/video is currently unavailable.")
    if not settings.jaas_app_id or not settings.jaas_key_id or not settings.jaas_private_key_path:
        raise AppError(503, "MEDIA_UNAVAILABLE", "Voice/video is not configured.")

    room = await svc.get_room_for(session, user, room_id)
    member = await svc.member_of(session, room.id, user.id)
    if member is None or member.status in {"left", "removed"}:
        raise AppError(403, "NOT_A_MEMBER", "You are not a member of this room.")

    try:
        private_key = Path(settings.jaas_private_key_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise AppError(503, "MEDIA_UNAVAILABLE", "Voice/video is not configured.") from None

    now = int(time.time())
    # JaaS tokens use RS256 and a room claim; never return the key or expose it to the browser.
    claims = {
        "aud": "jitsi",
        "iss": "chat",
        "sub": settings.jaas_app_id,
        "room": str(room.id),
        "iat": now,
        "nbf": now - 5,
        "exp": now + 60 * 60,
        "context": {
            "user": {
                "id": str(user.id),
                "name": user.display_name,
                "moderator": bool(room.host_user_id == user.id),
            },
            "features": {
                "recording": False,
                "livestreaming": False,
                "transcription": False,
                "outbound-call": False,
                "sip-outbound-call": False,
            },
        },
    }
    try:
        token = jwt.encode(
            claims, private_key, algorithm="RS256", headers={"kid": settings.jaas_key_id}
        )
    except (ValueError, TypeError):
        raise AppError(503, "MEDIA_UNAVAILABLE", "Voice/video is not configured.") from None
    return {"token": token, "room": str(room.id), "app_id": settings.jaas_app_id, "domain": "8x8.vc"}


@router.post("/{room_id}/companions")
async def add_companions(
    request: Request, room_id: uuid.UUID, body: CompanionsIn, user: CurrentUser, session: SessionDep
) -> RoomOut:
    """Demo only (D12): the host fills empty seats with labelled AI companions."""
    if not _demo(request):
        raise AppError(404, "NOT_FOUND", "Not Found")
    room, first = await companions.add_companions(session, user, room_id, body.count)
    await notify_room(request.app, room.id, "joined", first)
    return await _view(session, room, user, True)


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
