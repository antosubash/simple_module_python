"""Shared rate limiter (GH #347): policy, 429 shape, per-rule override, Redis fail-open."""

from __future__ import annotations

import httpx
import pytest
from simple_module_core.public_routes import PublicRouteRegistry
from simple_module_core.rate_limit import (
    InProcessWindowStore,
    RateLimitError,
    RateSpec,
    parse_rate,
)
from simple_module_hosting._rate_limit import RateLimitMiddleware, RedisWindowStore
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


class _Auth:
    """Stand-in for AuthMiddleware: marks a request signed in via a header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and (b"x-user", b"1") in scope["headers"]:
            scope.setdefault("state", {})["user"] = object()
        await self.app(scope, receive, send)


def _build(
    public: PublicRouteRegistry,
    *,
    public_rate: str | None = "3/minute",
    authenticated_rate: str | None = None,
    store=None,
) -> Starlette:
    async def ok(request):
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[
            Route("/api/pub/thing", ok),
            Route("/api/pub/fast", ok),
            Route("/api/private/thing", ok),
        ]
    )
    app.state.public_routes = public
    app.add_middleware(
        RateLimitMiddleware,
        public_rate=public_rate,
        authenticated_rate=authenticated_rate,
        store=store,
    )
    app.add_middleware(_Auth)  # outermost: runs first, like AuthMiddleware
    return app


def _client(app: Starlette) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def _public() -> PublicRouteRegistry:
    reg = PublicRouteRegistry()
    reg.add_prefix("/api/pub/")
    return reg


class TestParseRate:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("120/minute", RateSpec(120, 60)),
            ("5/second", RateSpec(5, 1)),
            ("10/10s", RateSpec(10, 10)),
            ("1000/hours", RateSpec(1000, 3600)),
            ("2/day", RateSpec(2, 86400)),
        ],
    )
    def test_valid(self, raw: str, expected: RateSpec) -> None:
        assert parse_rate(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "off", "none", "0", "0/minute"])
    def test_disabled(self, raw) -> None:
        assert parse_rate(raw) is None

    @pytest.mark.parametrize("raw", ["fast", "10", "10/fortnight", "/minute"])
    def test_invalid_raises(self, raw: str) -> None:
        with pytest.raises(RateLimitError):
            parse_rate(raw)

    def test_public_rule_validates_rate_at_registration(self) -> None:
        with pytest.raises(RateLimitError):
            PublicRouteRegistry().add_prefix("/x", rate="bogus")


class TestPolicy:
    async def test_anonymous_public_route_gets_429_with_retry_after(self) -> None:
        async with _client(_build(_public())) as c:
            for _ in range(3):
                assert (await c.get("/api/pub/thing")).status_code == 200
            r = await c.get("/api/pub/thing")
        assert r.status_code == 429
        assert 1 <= int(r.headers["retry-after"]) <= 60
        assert r.json()["retry_after"] == int(r.headers["retry-after"])
        assert r.headers["content-type"].startswith("application/json")

    async def test_authenticated_traffic_untouched(self) -> None:
        async with _client(_build(_public())) as c:
            for _ in range(10):
                r = await c.get("/api/pub/thing", headers={"x-user": "1"})
                assert r.status_code == 200

    async def test_authenticated_opt_in(self) -> None:
        app = _build(_public(), authenticated_rate="2/minute")
        async with _client(app) as c:
            codes = [
                (await c.get("/api/private/thing", headers={"x-user": "1"})).status_code
                for _ in range(3)
            ]
        assert codes == [200, 200, 429]

    async def test_non_public_route_untouched(self) -> None:
        async with _client(_build(_public())) as c:
            for _ in range(10):
                assert (await c.get("/api/private/thing")).status_code == 200

    async def test_per_rule_override_replaces_default(self) -> None:
        reg = PublicRouteRegistry()
        reg.add_exact("/api/pub/fast", rate="1/minute")
        reg.add_prefix("/api/pub/")
        async with _client(_build(reg)) as c:
            assert (await c.get("/api/pub/fast")).status_code == 200
            assert (await c.get("/api/pub/fast")).status_code == 429
            # a sibling still gets the default 3/minute — its own bucket
            for _ in range(3):
                assert (await c.get("/api/pub/thing")).status_code == 200
            assert (await c.get("/api/pub/thing")).status_code == 429

    async def test_rule_rate_off_exempts_rule(self) -> None:
        reg = PublicRouteRegistry()
        reg.add_prefix("/api/pub/", rate="off")
        async with _client(_build(reg)) as c:
            for _ in range(10):
                assert (await c.get("/api/pub/thing")).status_code == 200

    async def test_disabled_default_skips_limiting(self) -> None:
        async with _client(_build(_public(), public_rate="off")) as c:
            for _ in range(10):
                assert (await c.get("/api/pub/thing")).status_code == 200

    async def test_buckets_are_per_client_ip(self) -> None:
        app = _build(_public())
        transports = [
            httpx.ASGITransport(app=app, client=("1.1.1.1", 1)),
            httpx.ASGITransport(app=app, client=("2.2.2.2", 1)),
        ]
        a = httpx.AsyncClient(transport=transports[0], base_url="http://t")
        b = httpx.AsyncClient(transport=transports[1], base_url="http://t")
        async with a, b:
            for _ in range(3):
                await a.get("/api/pub/thing")
            assert (await a.get("/api/pub/thing")).status_code == 429
            assert (await b.get("/api/pub/thing")).status_code == 200


class TestInProcessStore:
    async def test_window_resets(self) -> None:
        clock = _FakeClock()
        store = InProcessWindowStore(clock=clock)
        spec = RateSpec(2, 60)
        assert (await store.hit("k", spec)).allowed
        assert (await store.hit("k", spec)).allowed
        denied = await store.hit("k", spec)
        assert not denied.allowed and denied.retry_after == 60
        clock.now += 61
        assert (await store.hit("k", spec)).allowed


class _FakeRedis:
    """Implements just the Lua script's contract: INCR + PEXPIRE + PTTL."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.calls = 0

    async def eval(self, script: str, numkeys: int, key: str, period_ms: int):
        self.calls += 1
        self.counts[key] = self.counts.get(key, 0) + 1
        return [self.counts[key], period_ms]


class _DeadRedis:
    calls = 0

    async def eval(self, *a, **k):
        type(self).calls += 1
        raise ConnectionError("redis down")


class TestRedisStore:
    async def test_counts_in_redis_and_limits(self) -> None:
        fake = _FakeRedis()
        app = _build(_public(), store=RedisWindowStore(fake))
        async with _client(app) as c:
            codes = [(await c.get("/api/pub/thing")).status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]
        assert fake.calls == 4
        assert any(k.startswith("sm:rl:public:") for k in fake.counts)

    async def test_retry_after_comes_from_pttl(self) -> None:
        store = RedisWindowStore(_FakeRedis())
        result = await store.hit("k", RateSpec(1, 30))
        assert result.retry_after == 30

    async def test_redis_down_fails_open_with_warning(self, caplog) -> None:
        app = _build(_public(), store=RedisWindowStore(_DeadRedis()))
        with caplog.at_level("WARNING", logger="simple_module.request_guard"):
            async with _client(app) as c:
                for _ in range(10):
                    assert (await c.get("/api/pub/thing")).status_code == 200
        warnings = [r for r in caplog.records if "failing open" in r.getMessage()]
        assert len(warnings) == 1  # throttled, not one per request

    async def test_redis_down_backs_off_instead_of_retrying_each_request(self) -> None:
        _DeadRedis.calls = 0
        now = [100.0]
        store = RedisWindowStore(_DeadRedis(), clock=lambda: now[0])
        for _ in range(20):
            assert (await store.hit("k", RateSpec(1, 60))).allowed
        assert _DeadRedis.calls == 1
        now[0] += 6  # backoff elapsed: Redis is probed again
        await store.hit("k", RateSpec(1, 60))
        assert _DeadRedis.calls == 2


class TestWiredIntoApp:
    async def test_real_pipeline_limits_registered_public_route(self, app, client) -> None:
        app.state.public_routes.add_exact("/health", rate="2/minute")
        codes = [(await client.get("/health")).status_code for _ in range(3)]
        assert 429 not in codes[:2]
        assert codes[2] == 429

    async def test_authenticated_client_untouched(self, app, authenticated_client) -> None:
        app.state.public_routes.add_exact("/health", rate="1/minute")
        for _ in range(4):
            assert (await authenticated_client.get("/health")).status_code != 429

    async def test_html_request_gets_error_page(self, app, client) -> None:
        app.state.public_routes.add_exact("/health", rate="1/minute")
        await client.get("/health")
        r = await client.get("/health", headers={"accept": "text/html", "x-inertia": "true"})
        assert r.status_code == 429
        assert r.json()["component"] == "Error"
        assert "retry-after" in r.headers
