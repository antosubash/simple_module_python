"""Development-only ``Server-Timing`` header: request time and SQL statements.

Every response in a development host carries::

    Server-Timing: app;dur=12.4, db;dur=3.1;desc="5 queries"

``app`` is the time from this middleware until the response starts (the
handler, every inner middleware and the commit); ``db`` is the time spent in
the database driver, and ``desc`` the number of statements. Browsers show both
in the network panel's Timing tab, and the page-perf audit
(``skills/simple-module-page-perf``) reads them to flag N+1 pages.

Never installed outside development: per-request timings help an attacker
time lookups (user enumeration, cache probing).
"""

from __future__ import annotations

import time

from simple_module_db.query_stats import track_queries
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

__all__ = ["SERVER_TIMING_HEADER", "ServerTimingMiddleware", "format_server_timing"]

SERVER_TIMING_HEADER = "Server-Timing"
_SCOPE_HTTP = "http"
_MSG_RESPONSE_START = "http.response.start"


def format_server_timing(app_seconds: float, db_seconds: float, queries: int) -> str:
    """Render the header value (durations in milliseconds, one decimal)."""
    noun = "query" if queries == 1 else "queries"
    return (
        f'app;dur={app_seconds * 1000:.1f}, db;dur={db_seconds * 1000:.1f};desc="{queries} {noun}"'
    )


class ServerTimingMiddleware:
    """Add a ``Server-Timing`` header with app time and SQL statement totals."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != _SCOPE_HTTP:
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        with track_queries() as stats:

            async def send_with_timing(message: Message) -> None:
                if message["type"] == _MSG_RESPONSE_START:
                    MutableHeaders(scope=message).append(
                        SERVER_TIMING_HEADER,
                        format_server_timing(
                            time.perf_counter() - start, stats.seconds, stats.count
                        ),
                    )
                await send(message)

            await self.app(scope, receive, send_with_timing)
