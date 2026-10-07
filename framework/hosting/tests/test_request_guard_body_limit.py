"""Request-body size guard (GH #345): Content-Length, chunked, per-path, 413 shape."""

from __future__ import annotations

import httpx
import pytest
from simple_module_core.body_limits import BodyLimitRegistry
from simple_module_hosting._body_limit import BodyLimitMiddleware
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

LIMIT = 1000


def _build(registry: BodyLimitRegistry | None = None, *, limit: int = LIMIT) -> Starlette:
    async def echo(request: Request):
        body = await request.body()
        return JSONResponse({"n": len(body)})

    async def chunked_error(request: Request):
        # Mimics FastAPI turning any body-read error into its own 400.
        try:
            await request.body()
        except Exception:
            return JSONResponse({"detail": "parse error"}, status_code=400)
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[
            Route("/api/echo", echo, methods=["POST"]),
            Route("/api/upload", echo, methods=["POST"]),
            Route("/api/swallow", chunked_error, methods=["POST"]),
        ]
    )
    app.add_middleware(BodyLimitMiddleware, max_bytes=limit, registry=registry)
    return app


def _client(app: Starlette) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _chunks(total: int, size: int = 100):
    sent = 0
    while sent < total:
        n = min(size, total - sent)
        sent += n
        yield b"x" * n


class TestContentLength:
    async def test_within_limit_passes(self) -> None:
        async with _client(_build()) as c:
            r = await c.post("/api/echo", content=b"x" * LIMIT)
        assert r.status_code == 200 and r.json() == {"n": LIMIT}

    async def test_over_limit_refused_before_route_runs(self) -> None:
        reached = False

        async def spy(request: Request):
            nonlocal reached
            reached = True
            return JSONResponse({})

        app = Starlette(routes=[Route("/api/echo", spy, methods=["POST"])])
        app.add_middleware(BodyLimitMiddleware, max_bytes=LIMIT)
        async with _client(app) as c:
            r = await c.post("/api/echo", content=b"x" * (LIMIT + 1))
        assert r.status_code == 413
        assert r.json()["max_bytes"] == LIMIT
        assert not reached


class TestChunked:
    async def test_chunked_over_limit_refused(self) -> None:
        async with _client(_build()) as c:
            r = await c.post("/api/echo", content=_chunks(LIMIT * 3))
        assert r.status_code == 413

    async def test_chunked_within_limit_passes(self) -> None:
        async with _client(_build()) as c:
            r = await c.post("/api/echo", content=_chunks(LIMIT))
        assert r.status_code == 200 and r.json() == {"n": LIMIT}

    async def test_app_that_converts_read_error_to_400_still_gets_413(self) -> None:
        async with _client(_build()) as c:
            r = await c.post("/api/swallow", content=_chunks(LIMIT * 3))
        assert r.status_code == 413

    async def test_lying_content_length_is_still_counted(self) -> None:
        # Declares a small body, streams a large one.
        async with _client(_build()) as c:
            r = await c.post(
                "/api/echo",
                content=_chunks(LIMIT * 3),
                headers={"content-length": "10"},
            )
        assert r.status_code in (413, 400)  # h11 may reject the mismatch first


class TestPerPathOverride:
    async def test_override_raises_ceiling_for_one_path(self) -> None:
        reg = BodyLimitRegistry()
        reg.add_exact("/api/upload", LIMIT * 10, methods={"POST"})
        async with _client(_build(reg)) as c:
            big = b"x" * (LIMIT * 5)
            assert (await c.post("/api/upload", content=big)).status_code == 200
            assert (await c.post("/api/echo", content=big)).status_code == 413

    async def test_callable_limit_receives_app(self) -> None:
        reg = BodyLimitRegistry()
        reg.add_prefix("/api/upload", lambda app: 50)
        async with _client(_build(reg)) as c:
            assert (await c.post("/api/upload", content=b"x" * 51)).status_code == 413
            assert (await c.post("/api/upload", content=b"x" * 50)).status_code == 200

    async def test_zero_override_means_unlimited(self) -> None:
        reg = BodyLimitRegistry()
        reg.add_prefix("/api/upload", 0)
        async with _client(_build(reg)) as c:
            assert (await c.post("/api/upload", content=b"x" * 50_000)).status_code == 200

    async def test_zero_global_disables_guard(self) -> None:
        async with _client(_build(limit=0)) as c:
            assert (await c.post("/api/echo", content=b"x" * 50_000)).status_code == 200

    def test_registry_first_match_wins_and_methods_scope(self) -> None:
        reg = BodyLimitRegistry()
        reg.add_regex(r"/a/\d+$", 5, methods={"POST"})
        reg.add_prefix("/a", 9)
        assert reg.limit_for("POST", "/a/1") == 5
        assert reg.limit_for("GET", "/a/1") == 9
        assert reg.limit_for("GET", "/b") is None
        with pytest.raises(ValueError):
            reg.add_prefix("/c", -1)


class TestWiredIntoApp:
    """Through the real pipeline: ordering, JSON-vs-page negotiation, module hook."""

    async def test_api_path_gets_json_413(self, client: httpx.AsyncClient) -> None:
        r = await client.post("/api/users/auth/login", content=b"x" * (10 * 1024 * 1024 + 1))
        assert r.status_code == 413
        assert r.headers["content-type"].startswith("application/json")
        assert r.json()["max_bytes"] == 10 * 1024 * 1024
        assert r.headers.get("x-correlation-id")  # outside CorrelationId

    async def test_browser_request_gets_error_page(self, app, client: httpx.AsyncClient) -> None:
        from fastapi import Form

        async def form_view(name: str = Form(...)):
            return {"name": name}

        app.add_api_route("/__guard_probe/form", form_view, methods=["POST"])
        app.state.public_routes.add_exact("/__guard_probe/form")
        big = b"name=" + b"x" * (10 * 1024 * 1024 + 1)
        form = {"content-type": "application/x-www-form-urlencoded"}
        # Plain browser navigation: the HTML error page.
        r = await client.post(
            "/__guard_probe/form", content=big, headers={**form, "accept": "text/html"}
        )
        assert r.status_code == 413
        assert "text/html" in r.headers["content-type"]
        # Inertia visit: the Error component, rendered with the full stack.
        r = await client.post(
            "/__guard_probe/form",
            content=big,
            headers={**form, "accept": "text/html", "x-inertia": "true"},
        )
        assert r.status_code == 413
        assert r.json()["component"] == "Error"
        assert r.json()["props"]["status"] == 413

    async def test_file_storage_upload_ceiling_follows_its_setting(self, app) -> None:
        reg = app.state.body_limits
        # 100 MB default + multipart headroom, resolved per request from settings.
        limit = reg.limit_for("POST", "/api/file-storage/upload", app)
        assert limit is not None and limit > 100 * 1024 * 1024
        assert reg.limit_for("GET", "/api/file-storage/upload", app) is None
