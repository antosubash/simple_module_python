"""#363: tenant from the subdomain — anonymous visitors, members, non-members."""

from __future__ import annotations

import httpx
import pytest
from fastapi import Depends
from simple_module_db import MultiTenantMixin, create_module_base, tenant_context
from simple_module_db.deps import get_db
from sqlalchemy import select
from sqlmodel import Field
from tenants.host_resolver import forget_hosts

_Base = create_module_base("subdom")


class _Page(_Base, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "subdom_page"
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(max_length=50)


@pytest.fixture
async def site(app):
    app.state.tenants.settings.subdomain_base = "example.com"
    forget_hosts()
    async with app.state.sm.db.engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    async def titles(db=Depends(get_db)):
        return (await db.execute(select(_Page.title))).scalars().all()

    app.add_api_route("/public/pages", titles, methods=["GET"])
    app.add_api_route("/api/private/pages", titles, methods=["GET"])
    app.state.public_routes.add_prefix("/public/", methods={"GET"})
    yield app
    app.state.tenants.settings.subdomain_base = ""
    forget_hosts()


async def _org_with_page(client, slug: str, app) -> dict:
    tenant = (await client.post("/api/tenants/", json={"name": slug, "slug": slug})).json()
    async with app.state.sm.db.session_factory() as db:
        with tenant_context(tenant["id"]):
            db.add(_Page(title=f"{slug}-home"))
            await db.commit()
    return tenant


def _anon(app, host: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"http://{host}")


async def test_anonymous_visitor_sees_the_subdomain_tenant(site, user_client):
    async with user_client("o@x.io") as (owner, _):
        await _org_with_page(owner, "acme", site)
        await _org_with_page(owner, "globex", site)
    async with _anon(site, "acme.example.com") as anon:
        assert (await anon.get("/public/pages")).json() == ["acme-home"]
    async with _anon(site, "globex.example.com") as anon:
        assert (await anon.get("/public/pages")).json() == ["globex-home"]


async def test_unknown_subdomain_binds_nothing(site, user_client):
    async with user_client("o@x.io") as (owner, _):
        await _org_with_page(owner, "acme", site)
    async with _anon(site, "nope.example.com") as anon:
        resp = await anon.get("/public/pages")
        assert resp.status_code == 403  # strict: no tenant -> tenant_required


async def test_suspended_subdomain_binds_nothing(site, user_client, authenticated_client):
    async with user_client("o@x.io") as (owner, _):
        tenant = await _org_with_page(owner, "acme", site)
    await authenticated_client.post(f"/api/tenants/admin/{tenant['id']}/suspend")
    async with _anon(site, "acme.example.com") as anon:
        assert (await anon.get("/public/pages")).status_code == 403


async def test_non_member_is_bound_only_on_public_routes(site, user_client):
    async with user_client("o@x.io") as (owner, _), user_client("n@x.io") as (outsider, _):
        await _org_with_page(owner, "acme", site)
        outsider.base_url = httpx.URL("http://acme.example.com")
        assert (await outsider.get("/public/pages")).json() == ["acme-home"]
        assert (await outsider.get("/api/private/pages")).status_code == 403


async def test_member_on_their_subdomain_gets_their_role(site, user_client):
    async with user_client("o@x.io") as (owner, _):
        await _org_with_page(owner, "acme", site)
        await _org_with_page(owner, "globex", site)  # active in the session now
        owner.base_url = httpx.URL("http://acme.example.com")
        assert (await owner.get("/api/private/pages")).json() == ["acme-home"]
        members = await owner.get("/api/tenants/current/members")
        assert members.status_code == 200 and members.json()[0]["role"] == "owner"
