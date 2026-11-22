"""Request guards use the reloaded host snapshot without rebuilding middleware."""

import httpx
from fastapi import FastAPI, Request
from settings.core.invalidation import reload_package
from simple_module_core.eventing.events import EventBus
from simple_module_core.settings.module_settings import module_settings_registry
from simple_module_core.web.body_limits import BodyLimitRegistry
from simple_module_core.web.cors import CorsPolicy, CorsPolicyRegistry
from simple_module_core.web.public_routes import PublicRouteRegistry
from simple_module_hosting.config._host_services import _HostServices
from simple_module_hosting.config.host_settings import HostSettings
from simple_module_hosting.pipeline._body_limit import BodyLimitMiddleware
from simple_module_hosting.pipeline._cors import CorsMiddleware
from simple_module_hosting.rate_limit._rate_limit import RateLimitMiddleware


class Store:
    def __init__(self, **rows):
        self.rows = rows

    async def get_overrides(self, package):
        assert package == "host"
        return self.rows


def build():
    app = FastAPI()
    app.state.host = _HostServices(HostSettings(rate_limit_public="off"))
    module_settings_registry(app).register("host", HostSettings)
    app.state.public_routes = PublicRouteRegistry()
    app.state.public_routes.add_prefix("/api/")
    app.state.cors_policies = CorsPolicyRegistry()
    limits = BodyLimitRegistry()
    limits.add_prefix("/api/large", 100)
    app.add_middleware(RateLimitMiddleware, public_rate="off")
    app.add_middleware(BodyLimitMiddleware, max_bytes=0, registry=limits)
    app.add_middleware(CorsMiddleware, registry=app.state.cors_policies)

    @app.post("/api/{path:path}")
    async def echo(request: Request):
        return {"size": len(await request.body())}

    return app


async def test_body_limit_reload_preserves_module_override():
    app = build()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.post("/api/test", content=b"12345")).status_code == 200
        await reload_package(app, EventBus(), Store(max_request_body_bytes=("4", "int")), "host")
        assert (await c.post("/api/test", content=b"12345")).status_code == 413
        assert (await c.post("/api/large", content=b"12345")).status_code == 200


async def test_rate_reload_replaces_public_and_authenticated_limits():
    app = build()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.post("/api/test")).status_code == 200
        await reload_package(
            app, EventBus(), Store(rate_limit_public=("1/minute", "string")), "host"
        )
        assert (await c.post("/api/test")).status_code == 200
        assert (await c.post("/api/test")).status_code == 429
        await reload_package(app, EventBus(), Store(rate_limit_public=("off", "string")), "host")
        assert (await c.post("/api/test")).status_code == 200


async def test_cors_reload_add_change_remove_and_module_rules():
    app = build()
    app.state.cors_policies.add_exact(
        "/api/module", CorsPolicy(origins=("https://module.example",))
    )
    headers = {"Origin": "https://a.example"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (
            "access-control-allow-origin"
            not in (await c.post("/api/test", headers=headers)).headers
        )
        await reload_package(
            app, EventBus(), Store(cors_allow_origins=('["https://a.example"]', "json")), "host"
        )
        assert (await c.post("/api/test", headers=headers)).headers[
            "access-control-allow-origin"
        ] == "https://a.example"
        await reload_package(
            app, EventBus(), Store(cors_allow_origins=('["https://b.example"]', "json")), "host"
        )
        assert (
            "access-control-allow-origin"
            not in (await c.post("/api/test", headers=headers)).headers
        )
        module = await c.post("/api/module", headers={"Origin": "https://module.example"})
        assert module.headers["access-control-allow-origin"] == "https://module.example"
        await reload_package(app, EventBus(), Store(), "host")
        assert (
            "access-control-allow-origin"
            not in (await c.post("/api/test", headers={"Origin": "https://b.example"})).headers
        )


async def test_all_cors_fields_reload_together():
    app = build()
    preflight = {
        "Origin": "https://app.example",
        "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "X-New",
    }
    rows = Store(
        cors_allow_origins=('["https://app.example"]', "json"),
        cors_allow_credentials=("false", "bool"),
        cors_allow_methods=('["PATCH"]', "json"),
        cors_allow_headers=('["X-New"]', "json"),
        cors_expose_headers=('["X-Result"]', "json"),
        cors_max_age=("42", "int"),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        await reload_package(app, EventBus(), rows, "host")
        response = await c.options("/api/test", headers=preflight)
        assert response.status_code == 200
        assert response.headers["access-control-allow-methods"] == "PATCH"
        assert "X-New" in response.headers["access-control-allow-headers"]
        assert response.headers["access-control-max-age"] == "42"
        assert "access-control-allow-credentials" not in response.headers
        response = await c.post("/api/test", headers={"Origin": "https://app.example"})
        assert response.headers["access-control-expose-headers"] == "X-Result"
        await reload_package(
            app, EventBus(), Store(cors_allow_origins=('["https://app.example"]', "json")), "host"
        )
        response = await c.options("/api/test", headers=preflight)
        assert response.status_code == 400  # old custom header is no longer allowed
        assert response.headers["access-control-max-age"] == "600"
        assert response.headers["access-control-allow-credentials"] == "true"


async def test_authenticated_rate_and_registered_rule_survive_reload():
    from simple_module_core.web.rate_limit import RateLimitRegistry, RateLimitRule

    app = build()
    app.state.rate_limit_rules = RateLimitRegistry()
    app.state.rate_limit_rules.add_exact("/api/module", RateLimitRule("1/minute", key="ip"))

    class Auth:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            scope.setdefault("state", {})["user"] = object()
            await self.app(scope, receive, send)

    app.add_middleware(Auth)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.post("/api/test")).status_code == 200
        await reload_package(
            app, EventBus(), Store(rate_limit_authenticated=("1/minute", "string")), "host"
        )
        assert (await c.post("/api/test")).status_code == 200
        assert (await c.post("/api/test")).status_code == 429
        await reload_package(app, EventBus(), Store(), "host")
        assert (await c.post("/api/test")).status_code == 200
        assert (await c.post("/api/module")).status_code == 200
        assert (await c.post("/api/module")).status_code == 429


def test_inflight_request_keeps_one_immutable_snapshot():
    from simple_module_hosting.pipeline._request_policy import request_policy

    app = build()
    scope = {"app": app}
    original = request_policy(scope)
    app.state.host.settings = HostSettings(max_request_body_bytes=1)
    assert request_policy(scope) is original
    assert request_policy({"app": app}).max_bytes == 1


async def test_rate_period_reload_does_not_reuse_an_old_long_window():
    app = build()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        await reload_package(app, EventBus(), Store(rate_limit_public=("1/day", "string")), "host")
        assert (await c.post("/api/test")).status_code == 200
        await reload_package(
            app, EventBus(), Store(rate_limit_public=("1/second", "string")), "host"
        )
        assert (await c.post("/api/test")).status_code == 200
        assert (await c.post("/api/test")).status_code == 429
