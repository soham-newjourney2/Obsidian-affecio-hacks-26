import uuid
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from backend.app.api.deps import CurrentUser, SessionDep
from backend.app.core.errors import AppError
from backend.app.models import Report
from backend.app.models.safety import REPORT_CATEGORIES
from backend.app.services import safety
from backend.app.services.rooms import member_of
from backend.app.ws.events import envelope

router = APIRouter(tags=["safety"])


class ConnectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reported_user: uuid.UUID | None = None
    room_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    category: Literal[REPORT_CATEGORIES]  # type: ignore[valid-type]
    description: str = Field(default="", max_length=500)


@router.post("/sessions/{session_id}/connections")
async def connect(
    session_id: uuid.UUID, body: ConnectIn, user: CurrentUser, session: SessionDep
) -> dict:
    return {"state": await safety.request(session, user, session_id, body.user_id)}


@router.post("/connections/{request_id}/accept", status_code=204)
async def accept(request_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    await safety.respond(session, user, request_id, accept=True)
    return Response(status_code=204)


@router.post("/connections/{request_id}/decline", status_code=204)
async def decline(request_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    await safety.respond(session, user, request_id, accept=False)
    return Response(status_code=204)


@router.get("/users/me/connections")
async def my_connections(user: CurrentUser, session: SessionDep) -> dict:
    return await safety.overview(session, user)


@router.post("/users/{user_id}/block", status_code=204)
async def block(user_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    await safety.block(session, user, user_id)
    return Response(status_code=204)


@router.post("/reports", status_code=201)
async def report(request: Request, body: ReportIn, user: CurrentUser, session: SessionDep) -> dict:
    row = await safety.report(session, user, body.model_dump(exclude_none=True))
    if row.room_id is not None:  # let the reporter's open table know it was received
        member = await member_of(session, row.room_id, user.id)
        if member is not None:
            notice = envelope("moderation.notice", row.room_id, {"kind": "report_received"})
            for conn in request.app.state.ws.connections(row.room_id):
                if conn.member_id == member.id:
                    await request.app.state.ws.send(conn, notice)
    return {"id": str(row.id), "status": row.status}


@router.get("/admin/reports")
async def admin_reports(request: Request, user: CurrentUser, session: SessionDep) -> list[dict]:
    if user.email_normalized not in request.app.state.settings.admins:
        raise AppError(403, "FORBIDDEN", "Admins only.")
    rows = await session.scalars(select(Report).order_by(Report.created_at.desc()).limit(200))
    return [
        {
            "id": str(r.id),
            "category": r.category,
            "description": r.description,
            "status": r.status,
            "reporter": str(r.reporter),
            "reported_user": str(r.reported_user) if r.reported_user else None,
            "room_id": str(r.room_id) if r.room_id else None,
            "message_id": str(r.message_id) if r.message_id else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
