"""#359 default tenant for single-tenant hosts; #364 work deferred past the request."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import BackgroundTasks, FastAPI
from pydantic import ValidationError
from simple_module_db import all_tenants, bind_current_tenant, current_tenant_id, tenant_context
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.host_settings import HostSettings
from simple_module_hosting.middleware import TenantMiddleware
from simple_module_hosting.settings import Settings


def _settings(**overrides) -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="testing",
        secret_key="test-secret-key",
        **overrides,
    )


def _tenant_middleware(app: FastAPI):
    return [m for m in app.user_middleware if m.cls is TenantMiddleware]


def test_single_tenant_host_binds_the_default_tenant():
    app = create_app(_settings(multi_tenant=False, default_tenant="main"))
    [mw] = _tenant_middleware(app)
    assert mw.kwargs == {"fixed": "main"}


def test_default_tenant_is_ignored_when_multi_tenant():
    app = create_app(_settings(multi_tenant=True, default_tenant="main"))
    [mw] = _tenant_middleware(app)
    assert "fixed" not in mw.kwargs


@pytest.mark.parametrize(
    ("multi_tenant", "default_tenant", "expected"),
    [(False, "main", "main"), (False, "", "default"), (True, "main", "default")],
)
def test_default_tenant_is_published_as_the_write_fallback(multi_tenant, default_tenant, expected):
    """Unbound / all_tenants() writes land in the install's own tenant."""
    app = create_app(_settings(multi_tenant=multi_tenant, default_tenant=default_tenant))
    assert app.state.sm.db.default_tenant_id == expected


def test_no_tenant_middleware_without_either():
    assert _tenant_middleware(create_app(_settings(multi_tenant=False))) == []


def test_default_tenant_must_be_a_valid_id():
    with pytest.raises(ValidationError):
        HostSettings(default_tenant="has space")


def test_default_tenant_cannot_be_the_platform_owner():
    from simple_module_db import PLATFORM_TENANT_ID

    with pytest.raises(ValidationError, match="reserved"):
        HostSettings(default_tenant=PLATFORM_TENANT_ID)


async def test_fixed_tenant_middleware_binds_every_request():
    seen = {}

    async def inner(scope, receive, send):
        seen["tenant"] = current_tenant_id.get()

    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "state": {}}
    await TenantMiddleware(inner, fixed="main")(scope, None, None)
    assert seen["tenant"] == "main"


async def test_background_tasks_run_inside_the_request_tenant():
    """FastAPI BackgroundTasks run inside TenantMiddleware: no capture needed."""
    seen = {}
    api = FastAPI()

    @api.get("/x")
    async def endpoint(background: BackgroundTasks):
        background.add_task(lambda: seen.setdefault("bg", current_tenant_id.get()))
        return {}

    api.add_middleware(TenantMiddleware, fixed="acme")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://t") as c:
        await c.get("/x")
    assert seen["bg"] == "acme"


async def test_bind_current_tenant_carries_the_tenant_past_the_request():
    with tenant_context("acme"):
        sync_job = bind_current_tenant(lambda: current_tenant_id.get())

        async def work():
            return current_tenant_id.get()

        async_job = bind_current_tenant(work)
    assert current_tenant_id.get() is None
    assert sync_job() == "acme"
    assert await async_job() == "acme"
    assert current_tenant_id.get() is None


async def test_bind_current_tenant_captures_the_bypass_too():
    from simple_module_db.tenancy import is_all_tenants

    with all_tenants():
        job = bind_current_tenant(is_all_tenants)
    assert job() is True
    assert await asyncio.to_thread(lambda: is_all_tenants()) is False
