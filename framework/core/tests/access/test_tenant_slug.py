"""``tenant_slug``: the soft lookup clients use to show a tenant's slug."""

from __future__ import annotations

from types import SimpleNamespace

from simple_module_core.access.tenancy import tenant_slug


async def test_none_when_no_module_publishes_a_lookup():
    app = SimpleNamespace(state=SimpleNamespace())
    assert await tenant_slug(app, "t1") is None


async def test_delegates_and_passes_through_an_unknown_id_as_none():
    async def slug(tenant_id: str) -> str | None:
        return {"t1": "acme"}.get(tenant_id)

    app = SimpleNamespace(state=SimpleNamespace(tenant_slug=slug))
    assert await tenant_slug(app, "t1") == "acme"
    assert await tenant_slug(app, "t2") is None
