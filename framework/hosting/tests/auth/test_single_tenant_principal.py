"""Request principals and flag helpers share the install's tenant (#1261)."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from simple_module_core.access.permissions import PermissionRegistry
from simple_module_core.access.principals import PrincipalRegistry
from simple_module_core.access.tenancy import TenancyMode
from simple_module_core.web.feature_flags import (
    FeatureFlagDefinition,
    FeatureFlagRegistry,
    is_flag_enabled,
)
from simple_module_db import current_tenant_id
from simple_module_db.engine.session import init_db
from simple_module_db.queries.principals import bind_principal_registry
from simple_module_hosting.auth.resource_deps import resource_principal
from simple_module_hosting.pipeline.tenancy import single_tenant_id


@pytest.mark.parametrize("default,expected", [(None, "default"), ("main", "main")])
@pytest.mark.parametrize("builder", [False, True])
@pytest.mark.parametrize("authenticated", [False, True])
async def test_single_tenant_principal_and_flags_use_install_id(
    default, expected, builder, authenticated
):
    db = init_db("sqlite+aiosqlite:///:memory:")
    if default:
        db.default_tenant_id = default
    permissions = PermissionRegistry()

    async def grants(request, user):
        return ["test.tenant"] if user.tenant_id == expected else []

    permissions.add_grant_source(grants)
    if builder:
        bind_principal_registry(db.session_factory, PrincipalRegistry(default_tenant=default))
    flags = FeatureFlagRegistry()
    flags.add(FeatureFlagDefinition("test.feature"))
    flags.set_override("test.feature", True, tenant_id=expected)
    app = FastAPI()
    app.state.sm = SimpleNamespace(
        db=db, permissions=permissions, feature_flags=flags, tenancy=TenancyMode.SINGLE
    )
    request = Request({"type": "http", "app": app})
    user = SimpleNamespace(id="user", roles=[], tenant_id=None)
    request.state.user = user if authenticated else None
    ambient = current_tenant_id.get()
    try:
        principal = await resource_principal(request)
        assert principal.tenant_id == expected
        assert single_tenant_id(app) == expected
        assert flags.is_enabled("test.feature", principal.tenant_id)
        assert is_flag_enabled(request, "test.feature")
        assert principal.permissions == ({"test.tenant"} if authenticated else set())
        if authenticated:
            del request.state.resource_principal
            assert await resource_principal(request) == principal
        assert user.tenant_id is None
        assert current_tenant_id.get() == ambient
    finally:
        await db.engine.dispose()


@pytest.mark.parametrize("tenant", [None, "acme"])
@pytest.mark.parametrize("authenticated", [False, True])
async def test_multi_tenant_principal_and_flags_keep_resolved_id(tenant, authenticated):
    app = FastAPI()
    flags = FeatureFlagRegistry()
    flags.add(FeatureFlagDefinition("test.feature"))
    flags.set_override("test.feature", True, tenant_id="default")
    app.state.sm = SimpleNamespace(
        db=SimpleNamespace(default_tenant_id="default"),
        permissions=None,
        feature_flags=flags,
        tenancy=TenancyMode.MULTI,
    )
    request = Request({"type": "http", "app": app})
    request.state.user = (
        SimpleNamespace(id="user", roles=[], tenant_id=None) if authenticated else None
    )
    request.state.tenant_id = tenant
    principal = await resource_principal(request)
    assert principal.tenant_id == (tenant if authenticated else None)
    assert not flags.is_enabled("test.feature", principal.tenant_id)
    assert not is_flag_enabled(request, "test.feature")
