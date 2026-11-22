"""Account authentication and resource membership stay separate on HTTP requests."""

import uuid

import pytest
from fastapi import Depends, Request
from simple_module_core.access.resources import ACTION_VIEW, ResourcePrincipal
from simple_module_db import MultiTenantMixin, create_module_base, tenant_context
from simple_module_db.deps import get_db
from simple_module_db.principals import principal_for
from simple_module_db.resource_policy import OwnedResourcePolicy
from simple_module_hosting.permissions import RequiresPermission
from simple_module_hosting.resource_deps import RequiresResource, resource_principal
from sqlalchemy import delete
from sqlmodel import Field, select
from tenants.models import Membership, Tenant
from tenants.resolution.host_resolver import forget_hosts
from tenants.resolution.resolver import forget
from users.models import Role, User, UserRole

_Base = create_module_base("principal_http_test")


class Document(_Base, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "principal_http_test_document"
    id: int | None = Field(default=None, primary_key=True)
    owner_id: str
    title: str
    visibility: str = "private"


POLICY = OwnedResourcePolicy(
    Document.owner_id, bypass_perm="test.manage", visibility_col=Document.visibility
)


@pytest.fixture
async def security_app(app):
    async with app.state.sm.db.engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    async def probe(
        request: Request,
        who: ResourcePrincipal = Depends(resource_principal),
        db=Depends(get_db),
    ):
        titles = []
        if request.state.tenant_id is not None:
            stmt = POLICY.filter(who, ACTION_VIEW, select(Document).order_by(Document.title))
            titles = [doc.title for doc in (await db.execute(stmt)).scalars()]
        cached = request.state.resource_principal
        return {
            "authenticated": request.state.user is not None,
            "user_id": who.user_id,
            "cached_user_id": cached.user_id,
            "permissions": sorted(who.permissions),
            "tenant_id": request.state.tenant_id,
            "titles": titles,
        }

    app.add_api_route("/api/principal-security", probe, methods=["GET"])
    app.add_api_route("/public/principal-security", probe, methods=["GET"])
    app.state.public_routes.add_prefix("/public/principal-security", methods={"GET"})

    def document_stmt(document_id: int):
        return select(Document).where(Document.id == document_id)

    @app.get("/public/principal-security/{document_id}")
    async def document(doc=Depends(RequiresResource(POLICY, ACTION_VIEW, document_stmt))):
        return {"title": doc.title}

    @app.get(
        "/api/principal-security/gated",
        dependencies=[Depends(RequiresPermission("test.http"))],
    )
    async def gated():
        return {"ok": True}

    app.state.sm.permissions.map_role("user", ["test.http"])
    yield app
    forget_hosts()


async def test_inactive_account_gets_401_on_permission_gated_route(security_app, tenant_client):
    async with tenant_client("member") as (client, _, user_id):
        async with security_app.state.sm.db.session_factory() as db:
            user = await db.get(User, uuid.UUID(user_id))
            user.is_active = False
            await db.commit()
        response = await client.get("/api/principal-security/gated")
        assert response.status_code == 401


async def test_nonmember_keeps_auth_but_gets_403_and_anonymous_resource_principal(
    security_app, tenant_client
):
    async with tenant_client("member") as (client, tenant_id, user_id):
        async with security_app.state.sm.db.session_factory() as db:
            await db.execute(delete(Membership).where(Membership.user_id == user_id))
            await db.commit()
        forget(user_id)
        headers = {"X-Tenant-ID": tenant_id}
        response = await client.get("/api/principal-security", headers=headers)
        assert response.status_code == 200
        assert response.json() == {
            "authenticated": True,
            "user_id": None,
            "cached_user_id": None,
            "permissions": [],
            "tenant_id": None,
            "titles": [],
        }
        assert (
            await client.get("/api/principal-security/gated", headers=headers)
        ).status_code == 200
        assert (
            await client.get("/api/tenants/current/members", headers=headers)
        ).status_code == 403


async def test_public_subdomain_removed_member_can_only_see_public_resources(
    security_app, tenant_client
):
    app = security_app
    app.state.tenants.settings.subdomain_base = "example.com"
    forget_hosts()
    async with tenant_client("member") as (client, tenant_id, user_id):
        async with app.state.sm.db.session_factory() as db:
            tenant = await db.get(Tenant, tenant_id)
            host = f"{tenant.slug}.example.com"
            private = Document(owner_id=user_id, title="private")
            public = Document(owner_id=user_id, title="public", visibility="public")
            with tenant_context(tenant_id):
                db.add_all([private, public])
                await db.commit()
        headers = {"Host": host}
        response = await client.get("/public/principal-security", headers=headers)
        assert response.status_code == 200
        assert response.json()["titles"] == ["private", "public"]
        private_url = f"/public/principal-security/{private.id}"
        assert (await client.get(private_url, headers=headers)).status_code == 200
        async with app.state.sm.db.session_factory() as db:
            await db.execute(delete(Membership).where(Membership.user_id == user_id))
            await db.commit()
        forget(user_id)
        response = await client.get("/public/principal-security", headers=headers)
        assert response.status_code == 200
        assert response.json() == {
            "authenticated": True,
            "user_id": None,
            "cached_user_id": None,
            "permissions": [],
            "tenant_id": tenant_id,
            "titles": ["public"],
        }
        assert (await client.get(private_url, headers=headers)).status_code == 404
        public_response = await client.get(
            f"/public/principal-security/{public.id}", headers=headers
        )
        assert public_response.status_code == 200
        assert public_response.json() == {"title": "public"}


@pytest.mark.parametrize("superuser", [False, True])
async def test_public_subdomain_nonmember_admin_retains_resource_bypass(
    security_app, tenant_client, superuser
):
    app = security_app
    app.state.tenants.settings.subdomain_base = "example.com"
    forget_hosts()
    async with tenant_client("member") as (client, tenant_id, user_id):
        async with app.state.sm.db.session_factory() as db:
            tenant = await db.get(Tenant, tenant_id)
            host = f"{tenant.slug}.example.com"
            user = await db.get(User, uuid.UUID(user_id))
            user.is_superuser = superuser
            role = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one()
            db.add(UserRole(user_id=user.id, role_id=role.id))
            await db.execute(delete(Membership).where(Membership.user_id == user_id))
            private = Document(owner_id="another-user", title="private")
            with tenant_context(tenant_id):
                db.add(private)
                await db.commit()
        forget(user_id)
        headers = {"Host": host}
        response = await client.get("/public/principal-security", headers=headers)
        assert response.status_code == 200
        data = response.json()
        held = frozenset(data.pop("permissions"))
        assert "*" in held
        assert data == {
            "authenticated": True,
            "user_id": user_id,
            "cached_user_id": user_id,
            "tenant_id": tenant_id,
            "titles": ["private"],
        }
        response = await client.get(f"/public/principal-security/{private.id}", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"title": "private"}
        async with app.state.sm.db.session_factory() as db:
            who = await principal_for(db, user_id, tenant_id)
        assert who == ResourcePrincipal(
            user_id, held, roles=frozenset({"admin", "user"}), tenant_id=tenant_id
        )
        async with app.state.sm.db.session_factory() as db:
            tenant = await db.get(Tenant, tenant_id)
            tenant.status = "suspended"
            await db.commit()
        forget_hosts()
        response = await client.get("/public/principal-security", headers=headers)
        assert response.status_code == 200
        assert response.json()["user_id"] is None
        assert response.json()["titles"] == []
        async with app.state.sm.db.session_factory() as db:
            assert await principal_for(db, user_id, tenant_id) is None
            assert await principal_for(db, user_id, "missing") is None
