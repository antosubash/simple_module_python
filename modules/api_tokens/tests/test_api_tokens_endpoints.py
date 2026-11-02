"""Who may manage tokens, and how: session only, CSRF on every mutation."""

from __future__ import annotations

from _api_tokens_support import (
    CSRF_HEADERS,
    INERTIA_HEADERS,
    PAT_URL,
    SERVICE_URL,
    create_pat,
)

BODY = {"name": "x", "scopes": ["api_tokens.use"], "expires_in_days": 7}


async def test_a_token_cannot_create_list_or_revoke_tokens(actor, bearer):
    async with actor() as user:
        created = await create_pat(user.client, ["api_tokens.use"])
    token, token_id = created["token"], created["item"]["id"]

    assert (await bearer("GET", PAT_URL, token)).status_code == 403
    assert (
        await bearer("POST", PAT_URL, token, json=BODY, headers=CSRF_HEADERS)
    ).status_code == 403
    revoke = await bearer("POST", f"{PAT_URL}{token_id}/revoke", token, headers=CSRF_HEADERS)
    assert revoke.status_code == 403
    assert (await bearer("GET", "/api-tokens/", token)).status_code == 403


async def test_an_admin_token_cannot_reach_the_admin_endpoints(actor, bearer):
    async with actor(admin=True) as a:
        token = (await create_pat(a.client, ["api_tokens.manage", "api_tokens.use"]))["token"]
    assert (await bearer("GET", "/api/api_tokens/admin/tokens", token)).status_code == 403
    body = {**BODY, "roles": []}
    assert (
        await bearer("POST", SERVICE_URL, token, json=body, headers=CSRF_HEADERS)
    ).status_code == 403


async def test_cookie_mutations_require_the_csrf_token(actor):
    async with actor() as user:
        assert (await user.client.post(PAT_URL, json=BODY)).status_code == 403
        wrong = await user.client.post(PAT_URL, json=BODY, headers={"X-CSRF-Token": "nope"})
        assert wrong.status_code == 403
        made = await user.client.post(PAT_URL, json=BODY, headers=CSRF_HEADERS)
        assert made.status_code == 201
        token_id = made.json()["item"]["id"]
        assert (await user.client.post(f"{PAT_URL}{token_id}/revoke")).status_code == 403


async def test_secret_is_returned_once_and_never_listed(actor):
    async with actor() as user:
        created = await create_pat(user.client, ["api_tokens.use"])
        listed = (await user.client.get(PAT_URL)).json()
    assert len(listed) == 1
    item = listed[0]
    assert "token" not in item and "token_hash" not in item
    assert created["token"].startswith(item["prefix"])
    assert created["token"] not in str(listed)


async def test_users_see_and_revoke_only_their_own_tokens(actor):
    async with actor() as alice, actor() as bob:
        mine = await create_pat(alice.client, ["api_tokens.use"])
        assert (await bob.client.get(PAT_URL)).json() == []
        stolen = await bob.client.post(
            f"{PAT_URL}{mine['item']['id']}/revoke", headers=CSRF_HEADERS
        )
        assert stolen.status_code == 404


async def test_admin_lists_and_revokes_tokens_in_the_tenant(actor):
    async with actor(admin=True) as a:
        async with actor(tenant_id=a.tenant_id) as member:
            theirs = await create_pat(member.client, ["api_tokens.use"])
        listed = (await a.client.get("/api/api_tokens/admin/tokens")).json()
        row = next(r for r in listed if r["id"] == theirs["item"]["id"])
        assert row["owner_email"].startswith("user-")

        revoked = await a.client.post(
            f"/api/api_tokens/admin/tokens/{row['id']}/revoke", headers=CSRF_HEADERS
        )
        assert revoked.status_code == 200
        assert revoked.json()["revoked_at"] is not None


async def test_admin_cannot_see_another_tenants_tokens(actor):
    async with actor(admin=True) as a, actor() as outsider:
        theirs = await create_pat(outsider.client, ["api_tokens.use"])
        listed = (await a.client.get("/api/api_tokens/admin/tokens")).json()
        assert theirs["item"]["id"] not in {r["id"] for r in listed}
        foreign = await a.client.post(
            f"/api/api_tokens/admin/tokens/{theirs['item']['id']}/revoke", headers=CSRF_HEADERS
        )
        assert foreign.status_code == 404


async def test_pages_render_with_their_props(actor):
    async with actor(admin=True) as a:
        page = await a.client.get("/api-tokens/", headers=INERTIA_HEADERS)
        assert page.status_code == 200, page.text
        props = page.json()["props"]
        assert "feature_flags.view" in props["scopes"]
        assert "*" not in props["scopes"]
        assert props["csrf_token"]

        admin = await a.client.get("/admin/api-tokens/", headers=INERTIA_HEADERS)
        assert admin.status_code == 200, admin.text
        assert "admin" not in admin.json()["props"]["roles"]

    async with actor() as user:
        assert (await user.client.get("/admin/api-tokens/")).status_code == 403
        own = await user.client.get("/api-tokens/", headers=INERTIA_HEADERS)
        assert own.status_code == 200
        assert "feature_flags.view" not in own.json()["props"]["scopes"]


async def test_create_and_revoke_are_audited_without_the_hash(app, actor):
    from audit_log.models import AuditEntry
    from simple_module_db import ALL_TENANTS_OPTION
    from sqlalchemy import select

    async with actor() as user:
        created = await create_pat(user.client, ["api_tokens.use"])
        token_id = created["item"]["id"]
        await user.client.post(f"{PAT_URL}{token_id}/revoke", headers=CSRF_HEADERS)

    async with app.state.sm.db.session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(AuditEntry)
                    .where(AuditEntry.entity_type == "ApiToken", AuditEntry.entity_id == token_id)
                    .execution_options(**{ALL_TENANTS_OPTION: True})
                )
            )
            .scalars()
            .all()
        )
    actions = sorted(r.action for r in rows)
    assert actions == ["created", "updated"]
    blob = str([r.changes for r in rows])
    assert "token_hash" not in blob
    assert "revoked_at" in blob
