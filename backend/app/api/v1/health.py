from fastapi import APIRouter

from backend.app.core.config import get_settings
from backend.app.core.errors import AppError

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "live"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    if not (get_settings().frontend_dir / "index.html").is_file():
        raise AppError(503, "NOT_READY", "Service is not ready")
    return {"status": "ready"}
