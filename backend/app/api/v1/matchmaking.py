from fastapi import APIRouter, Request, Response

from backend.app.api.deps import CurrentUser, SessionDep
from backend.app.services import queue

router = APIRouter(prefix="/matchmaking", tags=["matchmaking"])


@router.post("/queue")
async def join_queue(request: Request, user: CurrentUser, session: SessionDep) -> dict:
    await queue.join(request.app, session, user)
    return queue.status(request.app, user)


@router.delete("/queue", status_code=204)
async def leave_queue(request: Request, user: CurrentUser) -> Response:
    await queue.leave(request.app, user)
    return Response(status_code=204)


@router.get("/status")
async def queue_status(request: Request, user: CurrentUser) -> dict:
    """Never exposes scores or anyone's profile: only your own state and plain labels."""
    return queue.status(request.app, user)
