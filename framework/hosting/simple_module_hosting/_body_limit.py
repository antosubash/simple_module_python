"""Request-body size guard (GH #345).

Pure ASGI. Refuses an oversized body *before* a route reads it, so the limit
protects the process and not just the database:

* ``Content-Length`` over the ceiling is refused outright, body unread.
* No (or a lying) ``Content-Length`` — chunked transfer — is caught by counting
  the bytes the app actually pulls through ``receive`` and aborting once the
  ceiling is crossed.

The ceiling is the global ``max_request_body_bytes`` unless a module declared a
per-path override with ``register_body_limits``.
"""

from __future__ import annotations

import logging

from simple_module_core.body_limits import BodyLimitRegistry
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from simple_module_hosting._error_handlers import _wants_json
from simple_module_hosting._request_guard_responses import send_guard_response

logger = logging.getLogger("simple_module.request_guard")

_MESSAGE = "Request body is too large."


class _BodyTooLargeError(Exception):
    pass


class BodyLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int,
        registry: BodyLimitRegistry | None = None,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.registry = registry

    def _ceiling(self, scope: Scope) -> int:
        override = None
        if self.registry is not None:
            override = self.registry.limit_for(scope["method"], scope["path"], scope.get("app"))
        return self.max_bytes if override is None else override

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._ceiling(scope)
        if limit <= 0:
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        too_big = (
            declared is not None
            and declared.isascii()
            and declared.isdigit()
            and int(declared) > limit
        )
        # A browser-shaped request is answered with the Inertia error page, which
        # needs the session / locale / shared props the layers *inside* this one
        # set up. So it is not refused here: the body read raises an
        # ``HTTPException(413)`` that the app's own handler renders in full.
        # (FastAPI re-raises HTTPException from body parsing untouched.) API
        # callers are refused right here, before anything runs.
        if not self._wants_json(scope):
            await self._handle_page(scope, receive, send, limit, too_big)
            return
        if too_big:
            self._log(scope, limit, int(declared))
            await self._refuse(scope, receive, send, limit)
            return

        seen = 0
        exceeded = False
        refused = False
        started = False

        async def counting_receive() -> Message:
            nonlocal seen, exceeded
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    exceeded = True
                    raise _BodyTooLargeError
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal refused, started
            if exceeded and not started:
                # The app is answering a body we cut off (often with a 400 from
                # its own parser). Swallow it; the 413 below is the real answer.
                if not refused:
                    refused = True
                    self._log(scope, limit, seen)
                    await self._refuse(scope, receive, send, limit)
                return
            # Once the app's own response has started it is passed through whole:
            # swallowing the rest would leave the client hanging on a half-sent
            # response. (Any exception it raises for the cut-off body is re-raised
            # below, which aborts the connection instead.)
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:
            if not exceeded or started:
                if exceeded:
                    self._log(scope, limit, seen)
                raise
        if exceeded and not refused and not started:
            self._log(scope, limit, seen)
            await self._refuse(scope, receive, send, limit)

    @staticmethod
    def _wants_json(scope: Scope) -> bool:
        return _wants_json(Request(scope))

    async def _handle_page(
        self, scope: Scope, receive: Receive, send: Send, limit: int, too_big: bool
    ) -> None:
        seen = 0

        async def receive_or_413() -> Message:
            nonlocal seen
            if too_big:
                self._log(scope, limit, seen)
                raise HTTPException(status_code=413, detail=_MESSAGE)
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    self._log(scope, limit, seen)
                    raise HTTPException(status_code=413, detail=_MESSAGE)
            return message

        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive_or_413, tracking_send)
        except HTTPException as exc:
            # Raised by a middleware that reads the body *outside* the router's
            # exception handling (e.g. a form gate). Without this it would
            # surface as a bare 500 from ServerErrorMiddleware.
            if exc.status_code != 413 or started:
                raise
            await self._refuse(scope, receive, send, limit)

    @staticmethod
    def _log(scope: Scope, limit: int, size: int) -> None:
        cid = scope.get("state", {}).get("correlation_id", "")
        logger.warning(
            "Request body over limit: %s %s (%d > %d bytes) correlation_id=%s",
            scope["method"],
            scope["path"],
            size,
            limit,
            cid,
        )

    @staticmethod
    async def _refuse(scope: Scope, receive: Receive, send: Send, limit: int) -> None:
        await send_guard_response(
            scope,
            receive,
            send,
            413,
            _MESSAGE,
            headers={"Connection": "close"},
            extra={"max_bytes": limit},
        )
