"""Admin read/unlink REST routes work with a ``users.manage`` token (#1178)."""

from __future__ import annotations

import uuid

import pytest
from _api_tokens_support import admin_session, bearer_client, make_admin, pat_for  # ty: ignore[import-not-found]
from _users_admin_support import _make_user
from feature_flags.core.constants import PERM_FEATURE_FLAGS_VIEW
from users.core.constants import Permissions
from users.models import OAuthAccount

_BASE = "/api/users/admin"


async def _pat(app, scopes: list[str]) -> str:
    return await pat_for(app, await admin_session(app), scopes)


async def _user_with_links(app, count: int, *, admin: bool = False) -> tuple[str, list[str]]:
    email = f"target-{uuid.uuid4().hex[:8]}@example.com"
    ids: list[str] = []
    async with app.state.sm.db.session_factory() as db:
        if admin:
            target = await make_admin(app, email)
        else:
            target = str((await _make_user(db, email)).id)
        for i in range(count):
            link = OAuthAccount(
                user_id=uuid.UUID(target),
                oauth_name="github",
                account_id=f"id-{uuid.uuid4().hex[:6]}-{i}",
                account_email="t@example.com",
                access_token="x",
            )
            db.add(link)
            await db.flush()
            ids.append(str(link.id))
        await db.commit()
    return target, ids


@pytest.mark.anyio
async def test_manage_token_reads_user_roles_and_links(app):
    token = await _pat(app, [Permissions.MANAGE])
    target, links = await _user_with_links(app, 2)
    async with bearer_client(app, token) as c:
        roles = await c.get(f"{_BASE}/roles")
        user = await c.get(f"{_BASE}/{target}")
        listed = await c.get(f"{_BASE}/{target}/linked-sign-ins")
    assert roles.status_code == 200, roles.text
    assert all({"id", "name"} <= set(r) for r in roles.json()) and roles.json()
    assert user.status_code == 200, user.text
    assert user.json()["id"] == target
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert {x["id"] for x in body["linked_sign_ins"]} == set(links)
    assert body["has_duplicate_linked_sign_ins"] is True


@pytest.mark.anyio
async def test_unknown_user_is_404(app):
    token = await _pat(app, [Permissions.MANAGE])
    async with bearer_client(app, token) as c:
        missing = str(uuid.uuid4())
        assert (await c.get(f"{_BASE}/{missing}")).status_code == 404
        assert (await c.get(f"{_BASE}/{missing}/linked-sign-ins")).status_code == 404


@pytest.mark.anyio
async def test_token_without_scope_is_403(app):
    token = await _pat(app, [PERM_FEATURE_FLAGS_VIEW])
    target, links = await _user_with_links(app, 1)
    async with bearer_client(app, token) as c:
        for method, url in (
            ("GET", f"{_BASE}/roles"),
            ("GET", f"{_BASE}/{target}"),
            ("GET", f"{_BASE}/{target}/linked-sign-ins"),
            ("DELETE", f"{_BASE}/{target}/linked-sign-ins/{links[0]}"),
        ):
            resp = await c.request(method, url)
            assert resp.status_code == 403, (url, resp.text)


@pytest.mark.anyio
async def test_unlink_removes_link_without_csrf(app):
    token = await _pat(app, [Permissions.MANAGE])
    target, links = await _user_with_links(app, 2)
    async with bearer_client(app, token) as c:
        resp = await c.delete(f"{_BASE}/{target}/linked-sign-ins/{links[0]}")
        assert resp.status_code == 204, resp.text
        remaining = (await c.get(f"{_BASE}/{target}/linked-sign-ins")).json()
    assert [x["id"] for x in remaining["linked_sign_ins"]] == [links[1]]


@pytest.mark.anyio
async def test_unlink_other_users_link_is_404(app):
    token = await _pat(app, [Permissions.MANAGE])
    target, _ = await _user_with_links(app, 1)
    _, other_links = await _user_with_links(app, 1)
    async with bearer_client(app, token) as c:
        resp = await c.delete(f"{_BASE}/{target}/linked-sign-ins/{other_links[0]}")
        assert resp.status_code == 404
        missing = await c.delete(f"{_BASE}/{target}/linked-sign-ins/{uuid.uuid4()}")
        assert missing.status_code == 404


@pytest.mark.anyio
async def test_unlink_keeps_privilege_guard_for_scoped_token(app):
    """A scoped token cannot unlink an administrator's sign-in, as in the view."""
    token = await _pat(app, [Permissions.MANAGE])
    target, links = await _user_with_links(app, 1, admin=True)
    async with bearer_client(app, token) as c:
        resp = await c.delete(f"{_BASE}/{target}/linked-sign-ins/{links[0]}")
    assert resp.status_code == 403, resp.text
