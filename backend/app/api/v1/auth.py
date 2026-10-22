from fastapi import APIRouter, Request, Response

from backend.app.api.deps import AuthDep, CurrentUser, SessionDep, client_ip
from backend.app.core.errors import AppError
from backend.app.core.security import create_access_token
from backend.app.models import User
from backend.app.schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut
from backend.app.services.auth import authenticate, register_user

router = APIRouter(prefix="/auth", tags=["auth"])

def invalid_credentials() -> AppError:
    return AppError(401, "INVALID_CREDENTIALS", "Incorrect email or password.")


def _token_response(request: Request, user: User) -> TokenOut:
    settings = request.app.state.settings
    token = create_access_token(
        user.id, settings.secret_key.get_secret_value(), settings.access_token_minutes
    )
    return TokenOut(
        access_token=token.token,
        expires_in=settings.access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/register", status_code=201)
async def register(request: Request, body: RegisterIn, session: SessionDep) -> TokenOut:
    request.app.state.limits["register"].check(client_ip(request))
    user = await register_user(session, body)
    return _token_response(request, user)


@router.post("/login")
async def login(request: Request, body: LoginIn, session: SessionDep) -> TokenOut:
    key = f"{client_ip(request)}|{body.email.strip().lower()}"
    request.app.state.limits["login"].check(key)
    user = await authenticate(session, body.email, body.password)
    if user is None:
        raise invalid_credentials()
    return _token_response(request, user)


@router.post("/logout", status_code=204)
async def logout(request: Request, auth: AuthDep) -> Response:
    request.app.state.denylist.revoke(auth.claims.jti, auth.claims.exp)
    return Response(status_code=204)


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
