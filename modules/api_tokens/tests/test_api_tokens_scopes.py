"""The scope cap: admins are capped, demotion shrinks, creation is bounded by the creator."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from _api_tokens_support import CSRF_HEADERS, FLAGS_URL, PAT_URL, create_pat
from fastapi import HTTPException
from starlette.requests import Request


async def test_admin_token_is_capped_by_its_scopes(actor, bearer):
    """An admin's token skips every admin shortcut: it is worth its scopes only."""
    async with actor(admin=True) as a:
        token = (await create_pat(a.client, ["feature_flags.view"]))["token"]

    assert (await bearer("GET", FLAGS_URL, token)).status_code == 200
    assert (await bearer("PUT", f"{FLAGS_URL}x", token, json={"enabled": True})).status_code == 403
    assert (await bearer("GET", "/api/users/admin", token)).status_code == 403
    # Role-only admin gates: the Doctor page and the /admin index.
    assert (await bearer("GET", "/admin/doctor/", token)).status_code == 403


async def _set_roles(app, user_id: str, names: list[str]) -> None:
    from sqlalchemy import delete, select
    from users.bootstrap import ensure_user_role
    from users.models import Role, UserRole

    async with app.state.sm.db.session_factory() as session:
        uid = uuid.UUID(user_id)
        await session.execute(delete(UserRole).where(UserRole.user_id == uid))
        for name in names:
            role = (
                await session.execute(select(Role).where(Role.name == name))
            ).scalar_one_or_none()
            if role is None:
                role = await ensure_user_role(session) if name == "user" else Role(name=name)
                session.add(role)
                await session.flush()
            session.add(UserRole(user_id=uid, role_id=role.id))
        await session.commit()


async def test_demoting_the_owner_shrinks_the_token(app, actor, bearer):
    async with actor(admin=True) as a:
        token = (await create_pat(a.client, ["feature_flags.view"]))["token"]
        assert (await bearer("GET", FLAGS_URL, token)).status_code == 200

        await _set_roles(app, a.user_id, ["user"])

    assert (await bearer("GET", FLAGS_URL, token)).status_code == 403


async def test_scopes_must_be_held_by_the_creator(actor):
    async with actor() as user:
        refused = await user.client.post(
            PAT_URL,
            json={"name": "x", "scopes": ["feature_flags.view"], "expires_in_days": 7},
            headers=CSRF_HEADERS,
        )
        assert refused.status_code == 422
        assert "feature_flags.view" in refused.json()["detail"]

        made = await user.client.post(
            PAT_URL,
            json={"name": "x", "scopes": ["users.self.profile"], "expires_in_days": 7},
            headers=CSRF_HEADERS,
        )
        assert made.status_code == 201, made.text
        assert made.json()["item"]["scopes"] == ["users.self.profile"]


async def test_scopes_cannot_be_empty_or_unregistered(actor):
    async with actor(admin=True) as a:
        empty = await a.client.post(
            PAT_URL, json={"name": "x", "scopes": [], "expires_in_days": 7}, headers=CSRF_HEADERS
        )
        assert empty.status_code == 422
        bogus = await a.client.post(
            PAT_URL,
            json={"name": "x", "scopes": ["*"], "expires_in_days": 7},
            headers=CSRF_HEADERS,
        )
        assert bogus.status_code == 422


async def test_lifetime_is_capped_by_the_setting(app, actor):
    app.state.api_tokens.settings.max_lifetime_days = 30
    async with actor(admin=True) as a:
        too_long = await a.client.post(
            PAT_URL,
            json={"name": "x", "scopes": ["feature_flags.view"], "expires_in_days": 31},
            headers=CSRF_HEADERS,
        )
        assert too_long.status_code == 422
        ok = await a.client.post(
            PAT_URL,
            json={"name": "x", "scopes": ["feature_flags.view"], "expires_in_days": 30},
            headers=CSRF_HEADERS,
        )
        assert ok.status_code == 201


async def test_require_permission_admin_shortcut_skips_tokens():
    """``auth.deps.require_permission`` admits an admin session but not an admin token."""
    from auth.contracts.schemas import UserContext
    from auth.deps import require_permission

    check = require_permission("x.write").dependency
    translator = SimpleNamespace(t=lambda key, **_: key)

    def request() -> Request:
        req = Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace())})
        req.state.resolved_permissions = set()  # what the capped resolution produced
        return req

    session_admin = UserContext(id="1", email="a@b", name="A", roles=["admin"])
    assert await check(request(), translator, session_admin) is None

    token_admin = UserContext(
        id="1", email="a@b", name="A", roles=["admin"], auth_kind="pat", scopes=["y.read"]
    )
    with pytest.raises(HTTPException) as exc:
        await check(request(), translator, token_admin)
    assert exc.value.status_code == 403
