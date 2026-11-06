from __future__ import annotations


async def test_module_registers_resolver(app):
    from tenants.resolution.resolver import resolve_tenant

    assert app.state.tenant_resolver is resolve_tenant
    assert app.state.tenants.entitlements is not None
