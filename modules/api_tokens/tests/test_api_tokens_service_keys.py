"""Service keys: roles chosen at creation, never admin, pinned to their tenant."""

from __future__ import annotations

from _api_tokens_support import CSRF_HEADERS, FLAGS_URL, SERVICE_URL
from starlette.requests import Request


async def _create_key(client, *, roles, scopes, days=30):
    return await client.post(
        SERVICE_URL,
        json={"name": "deployer", "roles": roles, "scopes": scopes, "expires_in_days": days},
        headers=CSRF_HEADERS,
    )


async def test_service_key_gets_its_roles_capped_by_its_scopes(app, actor, bearer):
    # Give the ``user`` role the read permission so the key's role grants it.
    app.state.sm.permissions.map_role("user", ["feature_flags.view"])
    async with actor(admin=True) as a:
        resp = await _create_key(a.client, roles=["user"], scopes=["feature_flags.view"])
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token"].startswith("smsk_")
    assert body["item"]["owner_user_id"] is None
    assert body["item"]["roles"] == ["user"]

    token = body["token"]
    assert (await bearer("GET", FLAGS_URL, token)).status_code == 200
    assert (await bearer("PUT", f"{FLAGS_URL}x", token, json={"enabled": True})).status_code == 403


async def test_scope_without_a_role_granting_it_grants_nothing(actor, bearer):
    async with actor(admin=True) as a:
        resp = await _create_key(a.client, roles=[], scopes=["feature_flags.view"])
    assert resp.status_code == 201
    assert (await bearer("GET", FLAGS_URL, resp.json()["token"])).status_code == 403


async def test_service_key_cannot_be_admin(actor):
    async with actor(admin=True) as a:
        resp = await _create_key(a.client, roles=["admin"], scopes=["feature_flags.view"])
        assert resp.status_code == 422
        assert "admin" in resp.json()["detail"]

        tenant_role = await _create_key(
            a.client, roles=["tenant:owner"], scopes=["feature_flags.view"]
        )
        assert tenant_role.status_code == 422


async def test_only_managers_create_service_keys(actor):
    async with actor() as user:
        resp = await _create_key(user.client, roles=[], scopes=["users.self.profile"])
    assert resp.status_code == 403


async def test_service_principal_is_pinned_to_its_tenant(app, actor):
    from api_tokens.resolver import resolve_api_token
    from tenants.resolver import resolve_tenant

    async with actor(admin=True) as a:
        resp = await _create_key(a.client, roles=["user"], scopes=["feature_flags.view"])
        token, home = resp.json()["token"], a.tenant_id
    async with actor(admin=True) as other:
        elsewhere = other.tenant_id

    def request(*extra: tuple[bytes, bytes]) -> Request:
        headers = [(b"authorization", f"Bearer {token}".encode()), *extra]
        return Request(
            {"type": "http", "method": "GET", "path": "/", "headers": headers, "app": app}
        )

    ctx = await resolve_api_token(request())
    assert ctx is not None
    assert ctx.id.startswith("svc:")
    assert ctx.roles == ["user"]
    assert ctx.tenant_id == home
    assert (ctx.auth_kind, ctx.scopes) == ("service", ["feature_flags.view"])

    # Asking for another tenant by header does not move it.
    req = request((b"x-tenant-id", elsewhere.encode()))
    req.state.user = ctx
    resolution = await resolve_tenant(req)
    assert resolution.tenant_id == home
