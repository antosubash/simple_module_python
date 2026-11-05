"""Platform permission resolution preserves credential scope and validity."""

from types import SimpleNamespace

import pytest
from simple_module_core.permissions import PermissionRegistry
from simple_module_hosting.permissions import resolve_principal_permissions


@pytest.mark.parametrize(
    "scopes, expected",
    [
        (None, {"global.read", "direct.read", "claim.read"}),
        (["global.read"], {"global.read"}),
        ([], set()),
    ],
)
async def test_platform_resolution_excludes_tenant_roles(scopes, expected):
    registry = PermissionRegistry()
    registry.map_role("editor", ["global.read"])
    registry.map_role("tenant:owner", ["tenant.read", "api_tokens.use"])

    async def direct_grants(request, user):
        return {"direct.read", "*"}

    registry.add_grant_source(direct_grants)
    user = SimpleNamespace(
        roles=["editor", "tenant:owner"],
        permissions=["claim.read", "*"],
        scopes=scopes,
        required_permission="api_tokens.use",
    )
    held = await resolve_principal_permissions(None, user, registry, include_tenant_roles=False)
    assert held == expected
    assert user.roles == ["editor", "tenant:owner"]
    assert "tenant:owner" in registry.role_map
    if scopes is None:
        assert await resolve_principal_permissions(None, user, registry) == {
            "global.read",
            "direct.read",
            "claim.read",
            "tenant.read",
            "api_tokens.use",
        }


async def test_platform_resolution_still_rejects_invalid_credential():
    registry = PermissionRegistry()
    registry.map_role("editor", ["global.read"])
    user = SimpleNamespace(roles=["editor"], required_permission="api_tokens.use")
    assert (
        await resolve_principal_permissions(None, user, registry, include_tenant_roles=False)
        == set()
    )
