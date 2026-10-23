"""App factory: settings, DB, middleware, error handlers, API routers, static frontend at "/"."""

import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.api.v1 import auth, health, meta, stories, users
from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import register_error_handlers
from backend.app.core.logging import RequestIdMiddleware, configure_logging
from backend.app.core.ratelimit import RateLimiter
from backend.app.core.security import TokenDenylist
from backend.app.db.session import create_engine, create_sessionmaker

API_PREFIX = "/api/v1"

# The Windows registry can map these to text/plain, which breaks ES modules and stylesheets.
for _type, _ext in (("text/javascript", ".js"), ("text/css", ".css"), ("image/svg+xml", ".svg")):
    mimetypes.add_type(_type, _ext)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    is_dev = settings.app_env == "development"
    app = FastAPI(
        title="ECHO",
        lifespan=lifespan,
        docs_url="/api/docs" if is_dev else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if is_dev else None,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = create_sessionmaker(engine)
    app.state.denylist = TokenDenylist()
    app.state.limits = {
        "register": RateLimiter(limit=settings.register_rate_limit, window_s=60 * 60),
        "login": RateLimiter(limit=settings.login_rate_limit, window_s=15 * 60),
    }

    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(users.router, prefix=API_PREFIX)
    app.include_router(meta.router, prefix=API_PREFIX)
    app.include_router(stories.router, prefix=API_PREFIX)
    # Mounted last so API routes take precedence.
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    return app


app = create_app()
