"""
Application middleware for logging, error handling, and security.
"""

import time
import uuid
from typing import Callable

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.exceptions import BaseAppException

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs incoming requests and response times."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.time()

        log = logger.bind(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else "unknown",
        )

        log.info("request_started")

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            log.info(
                "request_completed",
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2),
            )

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{round(duration * 1000, 2)}ms"
            return response

        except Exception as exc:
            duration = time.time() - start_time
            log.error(
                "request_failed",
                error=str(exc),
                duration_ms=round(duration * 1000, 2),
            )
            raise


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """Catches and formats all unhandled exceptions."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
        except BaseAppException as exc:
            logger.warning(
                "application_error",
                error=exc.message,
                status_code=exc.status_code,
            )
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": exc.message,
                    "detail": exc.detail,
                    "status_code": exc.status_code,
                },
            )
        except Exception as exc:
            logger.error("unhandled_error", error=str(exc), exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "detail": None,
                    "status_code": 500,
                },
            )
