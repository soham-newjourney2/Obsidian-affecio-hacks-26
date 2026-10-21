"""App factory: settings, middleware, error handlers, API routers, static frontend at "/"."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.api.v1 import health
from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import register_error_handlers
from backend.app.core.logging import RequestIdMiddleware, configure_logging

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    is_dev = settings.app_env == "development"
    app = FastAPI(
        title="ECHO",
        docs_url="/api/docs" if is_dev else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if is_dev else None,
    )
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    app.include_router(health.router, prefix=API_PREFIX)
    # Mounted last so API routes take precedence.
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    return app


app = create_app()
