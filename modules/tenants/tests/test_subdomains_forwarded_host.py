"""#528: behind a trusted proxy, the allowlisted forwarded host picks the subdomain tenant."""

from __future__ import annotations

import httpx
from fastapi import Depends
from simple_module_db import MultiTenantMixin, create_module_base, tenant_context
from simple_module_db.deps import get_db
from simple_module_hosting._forwarded_host import ForwardedHostMiddleware
from sqlalchemy import select
from sqlmodel import Field
from tenants.host_resolver import forget_hosts

_Base = create_module_base("fwdhost")
_PROXY_IP = "10.9.8.7"
_INTERNAL = "internal.local"
_ALLOWLIST = ["*.example.com"]


class _Page(_Base, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "fwdhost_page"
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(max_length=50)


async def _site(app, user_client):
    app.state.tenants.settings.subdomain_base = "example.com"
    forget_hosts()
    async with app.state.sm.db.engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    async def titles(db=Depends(get_db)):
        return (await db.execute(select(_Page.title))).scalars().all()

    app.add_api_route("/public/fwd-pages", titles, methods=["GET"])
    app.state.public_routes.add_prefix("/public/", methods={"GET"})
    async with user_client("o@x.io") as (owner, _):
        tenant = (await owner.post("/api/tenants/", json={"name": "acme", "slug": "acme"})).json()
    async with app.state.sm.db.session_factory() as db:
        with tenant_context(tenant["id"]):
            db.add(_Page(title="acme-home"))
            await db.commit()


def _via_proxy(app, peer: str) -> httpx.AsyncClient:
    wrapped = ForwardedHostMiddleware(app, trusted_hosts=_PROXY_IP, allowlist=_ALLOWLIST)
    transport = httpx.ASGITransport(app=wrapped, client=(peer, 1))
    return httpx.AsyncClient(transport=transport, base_url=f"http://{_INTERNAL}")


async def test_wildcard_allowlist_resolves_the_subdomain_tenant(app, user_client):
    await _site(app, user_client)
    try:
        headers = {"X-Forwarded-Host": "acme.example.com"}
        async with _via_proxy(app, _PROXY_IP) as client:
            assert (await client.get("/public/fwd-pages", headers=headers)).json() == ["acme-home"]
        # Same header from an untrusted peer: ignored, so no tenant is bound.
        async with _via_proxy(app, "198.51.100.1") as client:
            assert (await client.get("/public/fwd-pages", headers=headers)).status_code == 403
        # A host outside the allowlist never reaches the resolver.
        async with _via_proxy(app, _PROXY_IP) as client:
            forged = {"X-Forwarded-Host": "acme.evil.net"}
            assert (await client.get("/public/fwd-pages", headers=forged)).status_code == 403
    finally:
        app.state.tenants.settings.subdomain_base = ""
        forget_hosts()
