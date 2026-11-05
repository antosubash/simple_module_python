"""Development-only Server-Timing header: app time plus SQL statement count."""

from __future__ import annotations

import re

import httpx
import pytest
from simple_module_db.query_stats import install_query_stats
from simple_module_hosting._server_timing import ServerTimingMiddleware, format_server_timing
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.settings import Settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

_HEADER = re.compile(r'^app;dur=\d+\.\d, db;dur=\d+\.\d;desc="(\d+) quer(?:y|ies)"$')


def test_format_server_timing() -> None:
    assert format_server_timing(0.0124, 0.0031, 5) == 'app;dur=12.4, db;dur=3.1;desc="5 queries"'
    assert format_server_timing(0.001, 0.0, 1).endswith('desc="1 query"')


async def test_header_counts_the_requests_queries() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    install_query_stats(engine)

    async def three_queries(_request):
        async with engine.connect() as conn:
            for _ in range(3):
                await conn.execute(text("select 1"))
        return PlainTextResponse("ok")

    app = ServerTimingMiddleware(Starlette(routes=[Route("/", three_queries)]))
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            first = await client.get("/")
            second = await client.get("/")
    finally:
        await engine.dispose()

    for response in (first, second):
        match = _HEADER.match(response.headers["server-timing"])
        assert match, response.headers["server-timing"]
        # Per request, not cumulative across requests.
        assert match.group(1) == "3"


def _names(settings: Settings) -> tuple[str, ...]:
    return tuple(m.cls.__name__ for m in create_app(settings).user_middleware)


@pytest.mark.parametrize(("environment", "installed"), [("development", True), ("testing", False)])
def test_installed_only_in_development(environment: str, installed: bool) -> None:
    names = _names(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            environment=environment,
            secret_key="x" * 32,
        )
    )
    assert ("ServerTimingMiddleware" in names) is installed
    if installed:
        # Right inside request logging, so it times the whole pipeline.
        logging_at = names.index("RequestLoggingMiddleware")
        assert names[logging_at + 1] == "ServerTimingMiddleware"
