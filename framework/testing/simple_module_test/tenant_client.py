"""``tenant_client``: a signed-in member of a real tenant, with a chosen role.

For a module adopting ``MultiTenantMixin``: its tests need requests that act
for one tenant, as an ``owner``, ``admin`` or ``member`` there — the role that
reaches the principal as ``tenant:<role>``::

    async def test_members_can_read(tenant_client):
        async with tenant_client("member") as (client, tenant_id, user_id):
            resp = await client.get("/api/things")

    async def test_isolation(tenant_client):
        async with tenant_client() as a, tenant_client() as b:
            ...  # two tenants, two owners

    async with tenant_client("owner") as owner, tenant_client(
        "member", tenant_id=owner.tenant_id
    ) as member:
        ...  # two users of the same tenant

Requires the ``users`` and ``tenants`` modules. Both are imported inside the
fixture body, never at module scope, so this plugin still imports cleanly in
an app that has neither — the same rule ``authenticated_client`` follows.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, NamedTuple

import httpx
import pytest
from simple_module_core.tenancy import TenantRole
from sqlalchemy import select

from simple_module_test.session_cookie import forge_session_cookie


class TenantClient(NamedTuple):
    client: httpx.AsyncClient
    tenant_id: str
    user_id: str


async def create_user(app: Any, email: str) -> str:
    """A real, active, non-superuser ``users`` row with the ``user`` role; its id."""
    from users.models import Role, User, UserRole

    async with app.state.sm.db.session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password="x",
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        session.add(user)
        await session.flush()
        role = (await session.execute(select(Role).where(Role.name == "user"))).scalar_one_or_none()
        if role is not None:
            session.add(UserRole(user_id=user.id, role_id=role.id))
        await session.commit()
        return str(user.id)


async def _join(app: Any, user_id: str, email: str, role: TenantRole, tenant_id: str | None) -> str:
    from tenants.models import Membership, Tenant
    from tenants.resolver import forget

    async with app.state.sm.db.session_factory() as session:
        if tenant_id is None:
            tenant = Tenant(slug=f"t-{uuid.uuid4().hex[:12]}", name="Test Org")
            session.add(tenant)
            await session.flush()
            tenant_id = tenant.id
        session.add(Membership(tenant_id=tenant_id, user_id=user_id, role=role, email=email))
        await session.commit()
    forget(user_id)  # the resolver caches memberships per user
    return tenant_id


@asynccontextmanager
async def session_client(app: Any, data: dict[str, Any]) -> AsyncIterator[httpx.AsyncClient]:
    """An ``httpx`` client for ``app`` whose signed session cookie holds ``data``."""
    cookie = forge_session_cookie(app.state.sm.settings.secret_key, data)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        cookies={"session": cookie},
    ) as client:
        yield client


@pytest.fixture
def tenant_client(app: Any) -> Callable[..., AbstractAsyncContextManager[TenantClient]]:
    """Factory: ``tenant_client(role="owner", *, tenant_id=None, email=None)``.

    Creates a user and a membership with ``role`` — in a new tenant, or in
    ``tenant_id`` when given — and yields a :class:`TenantClient` whose session
    has that tenant active.
    """
    from tenants.constants import SESSION_ACTIVE_TENANT

    @asynccontextmanager
    async def factory(
        role: str = TenantRole.OWNER,
        *,
        tenant_id: str | None = None,
        email: str | None = None,
    ) -> AsyncIterator[TenantClient]:
        member_role = TenantRole(role)
        email = email or f"{member_role}-{uuid.uuid4().hex[:8]}@example.com"
        user_id = await create_user(app, email)
        tenant_id = await _join(app, user_id, email, member_role, tenant_id)
        data = {"user_id": user_id, SESSION_ACTIVE_TENANT: tenant_id}
        async with session_client(app, data) as client:
            yield TenantClient(client, tenant_id, user_id)

    return factory


__all__ = ["TenantClient", "create_user", "session_client", "tenant_client"]
