from fastapi import APIRouter

from backend.app.schemas.profile import ProfileOptionsOut, profile_options

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/interests")
async def interests() -> ProfileOptionsOut:
    """Every curated profile option list plus selection limits (public, static)."""
    return profile_options()
