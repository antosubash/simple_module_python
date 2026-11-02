"""Shared helpers for the api_tokens tests (fixtures live in ``conftest.py``)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from simple_module_core.tenancy import TenantRole

CSRF = "csrf-test-token"
CSRF_HEADERS = {"X-CSRF-Token": CSRF}
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}
PAT_URL = "/api/api_tokens/tokens/"
SERVICE_URL = "/api/api_tokens/admin/service-keys"
FLAGS_URL = "/api/feature_flags/"


@dataclass
class Actor:
    client: httpx.AsyncClient
    user_id: str
    tenant_id: str


async def join_tenant(app: Any, user_id: str, email: str, tenant_id: str | None = None) -> str:
    """Make *user_id* an owner of a new tenant (or of *tenant_id*); return its id."""
    from tenants.models import Membership, Tenant
    from tenants.resolver import forget

    async with app.state.sm.db.session_factory() as session:
        if tenant_id is None:
            tenant = Tenant(slug=f"t-{uuid.uuid4().hex[:12]}", name="Test Org")
            session.add(tenant)
            await session.flush()
            tenant_id = tenant.id
        session.add(
            Membership(tenant_id=tenant_id, user_id=user_id, role=TenantRole.OWNER, email=email)
        )
        await session.commit()
    forget(user_id)
    return tenant_id


async def make_admin(app: Any, email: str) -> str:
    from users.bootstrap import create_admin

    async with app.state.sm.db.session_factory() as session:
        result = await create_admin(session, email=email, password="pw-123456", full_name="Admin")
        return str(result.user.id)


async def create_pat(client: httpx.AsyncClient, scopes: list[str], *, days: int = 30) -> dict:
    """POST a personal token and return the response body (``token`` + ``item``)."""
    resp = await client.post(
        PAT_URL,
        json={"name": "ci", "scopes": scopes, "expires_in_days": days},
        headers=CSRF_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def update_token(app: Any, token_id: str, **values: Any) -> None:
    """Write columns of a token row directly (expiry, last use) for a test."""
    from api_tokens.models import ApiToken
    from simple_module_db import ALL_TENANTS_OPTION
    from sqlalchemy import update

    async with app.state.sm.db.session_factory() as session:
        await session.execute(
            update(ApiToken)
            .where(ApiToken.id == uuid.UUID(token_id))
            .values(**values)
            .execution_options(**{ALL_TENANTS_OPTION: True})
        )
        await session.commit()


async def load_token(app: Any, token_id: str):
    from api_tokens.models import ApiToken
    from simple_module_db import all_tenants

    async with app.state.sm.db.session_factory() as session:
        with all_tenants():
            return await session.get(ApiToken, uuid.UUID(token_id))
