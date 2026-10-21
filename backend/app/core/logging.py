"""Request-id middleware and access logging (request_id, route, status, latency only)."""

import logging
import time
import uuid

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_HEADER_KEY = REQUEST_ID_HEADER.lower().encode()

access_log = logging.getLogger("echo.access")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or "-"


class RequestIdMiddleware:
    """Assigns a server-generated id per request; incoming ids are ignored."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != _HEADER_KEY
                ]
                headers.append((_HEADER_KEY, request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            route = scope.get("route")
            access_log.info(
                "request_id=%s route=%s status=%s latency_ms=%.1f",
                request_id,
                getattr(route, "path", scope["path"]),
                status,
                (time.perf_counter() - started) * 1000,
            )
