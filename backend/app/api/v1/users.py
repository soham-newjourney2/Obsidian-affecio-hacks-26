from fastapi import APIRouter

from backend.app.api.deps import CurrentUser, SessionDep
from backend.app.core.errors import AppError
from backend.app.schemas.profile import ProfileIn, ProfileOut
from backend.app.services.profiles import get_profile, upsert_profile

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/profile")
async def read_my_profile(user: CurrentUser, session: SessionDep) -> ProfileOut:
    profile = await get_profile(session, user)
    if profile is None:
        raise AppError(404, "PROFILE_NOT_FOUND", "Profile not set up yet.")
    return ProfileOut.model_validate(profile)


@router.put("/me/profile")
async def write_my_profile(body: ProfileIn, user: CurrentUser, session: SessionDep) -> ProfileOut:
    return ProfileOut.model_validate(await upsert_profile(session, user, body))
