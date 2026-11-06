"""HTTP middleware used for request-level observability."""

import logging
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request without recording credentials or request bodies."""

    async def dispatch(self, request: Request, call_next):
        request_id = uuid4().hex[:12]
        started = time.perf_counter()
        client_host = request.client.host if request.client else "unknown"

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "request_failed request_id=%s method=%s path=%s client=%s duration_ms=%.2f",
                request_id,
                request.method,
                request.url.path,
                client_host,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "request_completed request_id=%s method=%s path=%s status=%s client=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            client_host,
            duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response
