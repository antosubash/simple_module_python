"""Security review round 1, pass 2: tenant pinning, bearer laundering, stored roles.

* M2 — a PAT acts in the tenant it was created in, never one named by a
  header, and only while its owner is still an active member there.
* M3 — a provider's bearer access token keeps its full rights but cannot
  manage API tokens, so it cannot be laundered into a year-long PAT.
* L5 — a service key's stored ``tenant:*`` / ``admin`` roles are dropped.
* Keycloak — no PAT for an account the resolver could never load.
* L1 — "revoke all my tokens".
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from _api_tokens_support import (
    CSRF,
    CSRF_HEADERS,
    FLAGS_URL,
    INERTIA_HEADERS,
    PAT_URL,
    create_pat,
    join_tenant,
    make_admin,
)
from simple_module_test.tenant_client import create_user

MEMBERS_URL = "/api/tenants/current/members"


async def _member_ids(resp: httpx.Response) -> set[str]:
    assert resp.status_code == 200, resp.text
    return {str(m["user_id"]) for m in resp.json()}


async def test_pat_is_pinned_to_its_tenant_whatever_the_header_says(app, actor, bearer):
    app.state.sm.settings.tenant_header = "X-Tenant-Id"
    async with actor() as u:
        token = (await create_pat(u.client, ["tenants.members.view"]))["token"]
        tenant_a = u.tenant_id
    # The same person also belongs to tenant B, alongside a stranger.
    tenant_b = await join_tenant(app, u.user_id, f"b-{uuid.uuid4().hex[:6]}@example.com")
    stranger = f"s-{uuid.uuid4().hex[:6]}@example.com"
    stranger_id = await create_user(app, stranger)
    await join_tenant(app, stranger_id, stranger, tenant_b)

    resp = await bearer("GET", MEMBERS_URL, token, headers={"X-Tenant-Id": tenant_b})
    members = await _member_ids(resp)
    assert stranger_id not in members  # tenant B's member list stays out of reach
    assert u.user_id in members  # it answered for tenant A
    assert tenant_a != tenant_b
    vary = resp.headers.get("vary", "")
    assert "Authorization" in vary
    assert "X-Tenant-Id" not in vary  # the header no longer decides


async def _remove_membership(app: Any, user_id: str, tenant_id: str) -> None:
    from sqlalchemy import delete
    from tenants.models import Membership
    from tenants.resolver import forget

    async with app.state.sm.db.session_factory() as session:
        await session.execute(
            delete(Membership).where(
                Membership.user_id == user_id, Membership.tenant_id == tenant_id
            )
        )
        await session.commit()
    forget(user_id)


async def test_pat_stops_working_once_the_owner_leaves_its_tenant(app, actor, bearer):
    async with actor(admin=True) as a:
        token = (await create_pat(a.client, ["feature_flags.view"]))["token"]
    assert (await bearer("GET", FLAGS_URL, token)).status_code == 200
    # Still a member elsewhere — but not of the tenant the token belongs to.
    await join_tenant(app, a.user_id, f"x-{uuid.uuid4().hex[:6]}@example.com")
    await _remove_membership(app, a.user_id, a.tenant_id)
    assert (await bearer("GET", FLAGS_URL, token)).status_code == 401


async def test_pat_stops_working_while_its_tenant_is_suspended(app, actor, bearer):
    from sqlalchemy import update
    from tenants.constants import TenantStatus
    from tenants.models import Tenant
    from tenants.resolver import forget

    async with actor(admin=True) as a:
        token = (await create_pat(a.client, ["feature_flags.view"]))["token"]
    async with app.state.sm.db.session_factory() as session:
        await session.execute(
            update(Tenant).where(Tenant.id == a.tenant_id).values(status=TenantStatus.SUSPENDED)
        )
        await session.commit()
    forget(None)
    assert (await bearer("GET", FLAGS_URL, token)).status_code == 401


async def _access_token(app: Any) -> tuple[str, str]:
    email = f"a-{uuid.uuid4().hex[:6]}@example.com"
    user_id = await make_admin(app, email)
    await join_tenant(app, user_id, email)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.post(
            "/api/users/auth/token", json={"email": email, "password": "pw-123456"}
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"], user_id


async def test_bearer_access_token_cannot_reach_token_management(app, bearer):
    access, _ = await _access_token(app)
    page = await bearer("GET", "/api-tokens/", access, headers=INERTIA_HEADERS)
    assert page.status_code == 403
    for method, url in (("GET", PAT_URL), ("POST", PAT_URL), ("POST", f"{PAT_URL}revoke-all")):
        resp = await bearer(
            method,
            url,
            access,
            headers=CSRF_HEADERS,
            json={"name": "x", "scopes": ["api_tokens.use"], "expires_in_days": 365},
        )
        assert resp.status_code == 403, (method, url, resp.text)
    admin = await bearer("GET", "/api/api_tokens/admin/tokens", access, headers=CSRF_HEADERS)
    assert admin.status_code == 403


async def test_bearer_access_token_keeps_its_full_rights(app, bearer):
    """No scope cap and no token guard for a provider's bearer: unchanged behaviour."""
    access, _ = await _access_token(app)
    assert (await bearer("GET", FLAGS_URL, access)).status_code == 200
    assert (await bearer("GET", "/api/tenants/", access)).status_code == 200


async def test_session_with_an_authorization_header_cannot_mint(actor):
    async with actor() as u:
        resp = await u.client.post(
            PAT_URL,
            json={"name": "x", "scopes": ["api_tokens.use"], "expires_in_days": 30},
            headers={**CSRF_HEADERS, "Authorization": "Basic Zm9vOmJhcg=="},
        )
    assert resp.status_code == 403


def test_service_key_drops_stored_tenant_and_admin_roles():
    from datetime import UTC, datetime, timedelta

    from api_tokens.constants import TokenKind
    from api_tokens.models import ApiToken
    from api_tokens.resolver import _service

    row = ApiToken(
        id=uuid.uuid4(),
        kind=TokenKind.SERVICE,
        name="k",
        prefix="smsk_abc",
        token_hash="h",
        scopes=["x.view"],
        roles=["admin", "tenant:owner", "tenant:admin", "user"],
        expires_at=datetime.now(UTC) + timedelta(days=1),
        tenant_id="t1",
    )
    assert _service(row).roles == ["user"]


async def test_no_pat_for_an_account_the_resolver_cannot_load(app, actor, monkeypatch):
    from api_tokens.service import ApiTokenService

    async def missing(self, user_id) -> bool:
        return False

    async with actor() as u:
        monkeypatch.setattr(ApiTokenService, "has_usable_account", missing)
        resp = await u.client.post(
            PAT_URL,
            json={"name": "x", "scopes": ["api_tokens.use"], "expires_in_days": 30},
            headers=CSRF_HEADERS,
        )
    assert resp.status_code == 400
    assert "local user record" in resp.json()["detail"]


async def test_has_usable_account(app):
    from api_tokens.service import ApiTokenService

    user_id = await create_user(app, f"u-{uuid.uuid4().hex[:6]}@example.com")
    async with app.state.sm.db.session_factory() as session:
        service = ApiTokenService(session)
        assert await service.has_usable_account(uuid.UUID(user_id)) is True
        assert await service.has_usable_account(uuid.uuid4()) is False


async def test_revoke_all_ends_every_token(actor, bearer):
    async with actor(admin=True) as a:
        first = (await create_pat(a.client, ["feature_flags.view"]))["token"]
        second = (await create_pat(a.client, ["feature_flags.view"]))["token"]
        # A token cannot pull the panic button for its owner.
        assert (await bearer("POST", f"{PAT_URL}revoke-all", first)).status_code == 403
        resp = await a.client.post(f"{PAT_URL}revoke-all", headers={"X-CSRF-Token": CSRF})
        assert resp.status_code == 200
        assert resp.json() == {"revoked": 2}
    assert (await bearer("GET", FLAGS_URL, first)).status_code == 401
    assert (await bearer("GET", FLAGS_URL, second)).status_code == 401
