"""``tenant_exists``: the soft lookup platform screens use to vet a tenant id."""

from __future__ import annotations

from types import SimpleNamespace

from simple_module_core.tenancy import tenant_exists


async def test_none_when_no_module_publishes_a_directory():
    app = SimpleNamespace(state=SimpleNamespace())
    assert await tenant_exists(app, "t1") is None


async def test_delegates_to_the_published_callable():
    async def exists(tenant_id: str) -> bool:
        return tenant_id == "t1"

    app = SimpleNamespace(state=SimpleNamespace(tenant_exists=exists))
    assert await tenant_exists(app, "t1") is True
    assert await tenant_exists(app, "t2") is False
