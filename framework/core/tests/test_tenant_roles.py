"""Shared tenant-role vocabulary (#380): modules map these without importing ``tenants``."""

from __future__ import annotations

import pytest
from simple_module_core import TENANT_ROLE_PREFIX, TenantRole, is_tenant_role, tenant_role


def test_prefix_and_names():
    assert TENANT_ROLE_PREFIX == "tenant:"
    assert [r.value for r in TenantRole] == ["owner", "admin", "member"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (TenantRole.OWNER, "tenant:owner"),
        (TenantRole.ADMIN, "tenant:admin"),
        ("member", "tenant:member"),
    ],
)
def test_tenant_role_builds_the_effective_role(name, expected):
    assert tenant_role(name) == expected


def test_tenant_role_rejects_unknown_names():
    with pytest.raises(ValueError, match="tenant role"):
        tenant_role("superuser")


def test_is_tenant_role():
    assert is_tenant_role("tenant:member")
    assert not is_tenant_role("admin")
