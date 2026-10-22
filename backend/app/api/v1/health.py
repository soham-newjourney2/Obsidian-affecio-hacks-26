import logging

from fastapi import APIRouter, Request
from sqlalchemy import text

from backend.app.core.errors import AppError

router = APIRouter(prefix="/health", tags=["health"])
log = logging.getLogger("echo.health")


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "live"}


@router.get("/ready")
async def ready(request: Request) -> dict[str, str]:
    state = request.app.state
    if not (state.settings.frontend_dir / "index.html").is_file():
        raise AppError(503, "NOT_READY", "Service is not ready")
    try:
        async with state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        log.warning("readiness: database unreachable")
        raise AppError(503, "NOT_READY", "Service is not ready") from None
    return {"status": "ready"}
