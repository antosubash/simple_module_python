"""ASGI middlewares for correlation IDs and structured request logging."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from simple_module_hosting.logging import correlation_id

_LOGGER_NAME = "simple_module.request"
_request_logger = logging.getLogger(_LOGGER_NAME)

_SCOPE_HTTP = "http"
_MSG_RESPONSE_START = "http.response.start"
_EVENT_REQUEST_STARTED = "request.started"
_EVENT_REQUEST_COMPLETED = "request.completed"

# Paths that produce noisy, low-value log entries
_QUIET_PREFIXES = ("/health", "/static/")


class CorrelationIdMiddleware:
    """Generate or propagate a correlation ID for every request.

    Reads the incoming ``X-Correlation-ID`` header (or generates a UUID4) and
    stores it in a :class:`~contextvars.ContextVar` so that every log record
    emitted during the request automatically includes the ID.  The same value
    is echoed back in the response header.
    """

    HEADER = "X-Correlation-ID"

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != _SCOPE_HTTP:
            await self.app(scope, receive, send)
            return

        cid = Headers(scope=scope).get(self.HEADER) or uuid.uuid4().hex

        async def send_with_header(message: Message) -> None:
            if message["type"] == _MSG_RESPONSE_START:
                headers = MutableHeaders(scope=message)
                headers[self.HEADER] = cid
            await send(message)

        token = correlation_id.set(cid)
        try:
            await self.app(scope, receive, send_with_header)
        finally:
            correlation_id.reset(token)


class RequestLoggingMiddleware:
    """Log every request/response pair with timing and status information."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != _SCOPE_HTTP:
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if any(path.startswith(p) for p in _QUIET_PREFIXES):
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        _request_logger.debug(
            _EVENT_REQUEST_STARTED,
            extra={"method": method, "path": path, "client_ip": client_ip},
        )

        status_code: int | None = None
        start = time.perf_counter()

        async def send_capture(message: Message) -> None:
            nonlocal status_code
            if message["type"] == _MSG_RESPONSE_START:
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_capture)
        finally:
            # Log completion even when the inner app raises, so 500s are observable.
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            _request_logger.info(
                _EVENT_REQUEST_COMPLETED,
                extra={
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                },
            )
