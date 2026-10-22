"""Standard error shape: {"error": {"code", "message", "request_id"}}. Never leaks internals."""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.core.logging import REQUEST_ID_HEADER, get_request_id

log = logging.getLogger("echo.errors")


class AppError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = get_request_id(request)
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers={**(headers or {}), REQUEST_ID_HEADER: request_id},
    )


async def _app_error(request: Request, exc: AppError) -> JSONResponse:
    return error_response(request, exc.status_code, exc.code, exc.message, exc.headers)


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # exc.detail is deliberately not echoed back.
    try:
        status = HTTPStatus(exc.status_code)
        code, message = status.name, status.phrase
    except ValueError:
        code, message = "ERROR", "Request failed"
    return error_response(request, exc.status_code, code, message)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(request, 422, "VALIDATION_ERROR", "Request validation failed")


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error request_id=%s", get_request_id(request))
    return error_response(request, 500, "INTERNAL_ERROR", "Something went wrong")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled_error)
