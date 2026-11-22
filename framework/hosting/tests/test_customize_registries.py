"""Host overrides run after the last hook and reach real request consumers."""

from dataclasses import dataclass
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Depends
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.access.resources import ResourceType
from simple_module_core.eventing.events import Event
from simple_module_core.web.rate_limit import RateLimitRule
from simple_module_core.web.setup_steps import SetupRegistry
from simple_module_hosting import app_builder, shared_props
from simple_module_hosting._inertia_shared import resolve_inertia_shared
from simple_module_hosting.permissions import RequiresPermission
from starlette.requests import Request


@dataclass
class Changed(Event):
    pass


class Example(ModuleBase):
    meta = ModuleMeta(name="Example")

    def register_public_routes(self, registry):
        registry.add_exact("/example/page")
        registry.add_prefix("/api/example/")

    def register_permissions(self, registry):
        registry.map_role("tenant:member", ["example.edit"])

    def register_rate_limits(self, registry):
        registry.add_exact("/api/example/limited", RateLimitRule("20/minute", key="ip"))

    def register_resource_types(self, registry):
        registry.register(ResourceType("example.item", object(), lambda key: "old"))

    def register_event_handlers(self, bus, app):
        bus.subscribe(Changed, self.handler)
        bus.subscribe_durable(Changed, self.handler, name="example.changed")

    async def handler(self, event, ctx=None):
        self.calls.append("old")

    def register_fallback_routes(self, router):
        # This is the last registration hook, later than middleware hooks.
        shared_props.register_inertia_shared_provider(
            self.app, lambda request: {"example": "module"}
        )

    def register_middleware(self, app):
        self.app = app

    def register_routes(self, api_router, view_router):
        @view_router.get("/example/page")
        async def page():
            return {"page": True}

        @api_router.get("/api/example/limited")
        async def limited():
            return {"ok": True}

        @api_router.get("/api/example/state")
        async def state(request: Request):
            sm = request.app.state.sm
            return {
                "permissions": sm.permissions.role_map["tenant:member"],
                "resource": sm.resource_types.get("example.item").select_by_id("7"),
                "shared": (await resolve_inertia_shared(request))["example"],
            }

        @api_router.get(
            "/api/example/edit", dependencies=[Depends(RequiresPermission("example.edit"))]
        )
        async def edit():
            return {"edited": True}


async def test_customize_reaches_all_consumers(settings, monkeypatch):
    # Readiness checks query the DB; this test exercises request registry consumers.
    async def ready(app):
        return True

    monkeypatch.setattr(SetupRegistry, "is_setup_complete", lambda self, app: ready(app))
    example = Example()
    example.calls = []
    discover = app_builder.discover_modules
    monkeypatch.setattr(
        app_builder,
        "discover_modules",
        lambda **kw: [*discover(**kw), example],
    )
    called = []

    async def replacement(event, ctx):
        called.append("replacement")

    def customize(app):
        sm = app.state.sm
        sm.public_routes.remove("/example/page", kind="exact")
        sm.permissions.revoke_role("tenant:member", "example.edit")
        app.state.rate_limit_rules.replace_exact(
            "/api/example/limited", RateLimitRule("1/minute", key="ip")
        )
        sm.resource_types.replace(ResourceType("example.item", object(), lambda key: "host"))
        sm.event_bus.unsubscribe(Changed, example.handler)
        sm.event_bus.replace_durable(Changed, replacement, name="example.changed")
        shared_props.replace_inertia_shared_prop(app, "example", lambda request: "host")
        called.append("customize")

    settings = settings.model_copy(update={"modules_enabled": ["Auth", "Users"]})
    app = app_builder.create_app(settings, customize=customize)
    try:

        async def member(request):
            if request.headers.get("X-Example-Member"):
                return SimpleNamespace(
                    id="member", email="member@example.test", name="Member", roles=["tenant:member"]
                )
            return None

        app.state.auth.principal_resolvers.append(member)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            page = await client.get("/example/page")
            assert page.status_code == 302
            assert "/users/login" in page.headers["location"]
            assert (await client.get("/api/example/limited")).status_code == 200
            assert (await client.get("/api/example/limited")).status_code == 429
            assert (await client.get("/api/example/state")).json() == {
                "permissions": [],
                "resource": "host",
                "shared": "host",
            }
            member_headers = {"X-Example-Member": "yes"}
            assert (
                await client.get("/api/example/edit", headers=member_headers)
            ).status_code == 403
            app.state.sm.permissions.set_role_overlay("tenant:member", ["example.edit"])
            assert (
                await client.get("/api/example/edit", headers=member_headers)
            ).status_code == 200
        await app.state.sm.event_bus.publish(Changed())
        await app.state.sm.event_bus.publish_durable_or_inline(Changed(), None)
        assert called == ["customize", "replacement"]
        assert example.calls == []
    finally:
        await app.state.sm.db.engine.dispose()


async def test_shared_replacement_requires_existing_resolved_key():
    from fastapi import FastAPI
    from simple_module_hosting._inertia_shared import merge_shared_prop_providers

    app = FastAPI()
    request = Request({"type": "http", "app": app})
    shared_props.replace_inertia_shared_prop(app, "missing", lambda request: "host")
    with pytest.raises(KeyError, match="missing"):
        await merge_shared_prop_providers(app, request, {})


async def test_shared_explicit_replacement_runs_last_and_awaits():
    from fastapi import FastAPI
    from simple_module_hosting import replace_inertia_shared_prop
    from simple_module_hosting._inertia_shared import merge_shared_prop_providers

    app = FastAPI()
    request = Request({"type": "http", "app": app})

    async def replacement(request):
        return "host"

    replace_inertia_shared_prop(app, "example", replacement)
    shared_props.register_inertia_shared_provider(app, lambda request: {"example": "first"})
    shared_props.register_inertia_shared_provider(app, lambda request: {"example": "later"})
    replace_inertia_shared_prop(app, "homeUrl", lambda request: "/host")
    replace_inertia_shared_prop(app, "auth", lambda request: {"custom": True})
    shared = {"auth": {"custom": False}}
    await merge_shared_prop_providers(app, request, shared)
    assert shared == {"example": "host", "homeUrl": "/host", "auth": {"custom": True}}


async def test_shared_replacement_error_propagates():
    from fastapi import FastAPI
    from simple_module_hosting._inertia_shared import merge_shared_prop_providers

    def broken(request):
        raise ValueError("host replacement failed")

    app = FastAPI()
    shared_props.replace_inertia_shared_prop(app, "example", broken)
    request = Request({"type": "http", "app": app})
    with pytest.raises(ValueError, match="host replacement failed"):
        await merge_shared_prop_providers(app, request, {"example": "module"})
