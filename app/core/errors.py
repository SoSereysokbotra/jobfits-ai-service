"""Error types + FastAPI exception handlers.

Every error leaves the service as the envelope from BUILD_PLAN.md §4.6:
    { "error": { "code": <ErrorCode>, "message": <str> } }
so the backend can react (e.g. fall back to its heuristics) instead of parsing
a raw stack trace.
"""

from __future__ import annotations

from enum import Enum
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("ai-service")


class ErrorCode(str, Enum):
    UNAUTHORIZED = "UNAUTHORIZED"
    BAD_REQUEST = "BAD_REQUEST"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_ERROR = "MODEL_ERROR"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    INTERNAL = "INTERNAL"


class AiServiceError(Exception):
    """Domain error that renders to the §4.6 envelope with a specific HTTP status."""

    def __init__(self, code: ErrorCode, message: str, status_code: int = 500) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _envelope(code: ErrorCode | str, message: str, status_code: int) -> JSONResponse:
    value = code.value if isinstance(code, ErrorCode) else code
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": value, "message": message}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire all handlers so no error escapes as an unstructured 500."""

    @app.exception_handler(AiServiceError)
    async def _handle_ai_error(_: Request, exc: AiServiceError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("AiServiceError %s: %s", exc.code.value, exc.message)
        return _envelope(exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope(ErrorCode.BAD_REQUEST, str(exc.errors()), 400)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = ErrorCode.UNAUTHORIZED if exc.status_code == 401 else ErrorCode.BAD_REQUEST
        return _envelope(code, str(exc.detail), exc.status_code)

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        return _envelope(ErrorCode.INTERNAL, "Internal server error", 500)
