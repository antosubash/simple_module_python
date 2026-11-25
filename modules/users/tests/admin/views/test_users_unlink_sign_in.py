"""Admin unlinking removes one owned identity, without revoking access (#1149)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from _users_admin_support import _make_user
from audit_log.models import AuditEntry
from sqlalchemy import select
from users.models import OAuthAccount, RefreshToken, User, UserAccessToken, UserRole


@pytest.fixture
async def linked_user(users_db):
    user = await _make_user(users_db, "linked@example.com", role_names=["user"])
    links = [
        OAuthAccount(
            user_id=user.id,
            oauth_name=provider,
            account_id=f"identity-{i}",
            account_email=user.email,
            access_token="secret-access",
            refresh_token="secret-refresh",
        )
        for i, provider in enumerate(["oidc", "oidc", "github"])
    ]
    users_db.add_all(links)
    users_db.add(UserAccessToken(user_id=user.id, token="existing-access"))
    users_db.add(
        RefreshToken(
            user_id=user.id,
            token="existing-refresh",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await users_db.commit()
    return user, links


async def _csrf(client, user_id):
    page = await client.get(f"/admin/users/{user_id}", headers={"X-Inertia": "true"})
    assert page.status_code == 200
    return {"X-CSRF-Token": page.json()["props"]["csrfToken"]}


async def _state(app, user_id):
    async with app.state.sm.db.session_factory() as db:
        user = await db.get(User, user_id)
        return (
            user.model_dump(),
            [
                [row.model_dump() for row in (await db.execute(select(model))).scalars()]
                for model in (UserRole, UserAccessToken, RefreshToken)
            ],
        )


@pytest.mark.anyio
async def test_unlink_only_owned_row_and_audit_actor(
    admin_client, users_app, users_db, linked_user
):
    user, links = linked_user
    headers = await _csrf(admin_client, user.id)
    before = await _state(users_app, user.id)

    response = await admin_client.delete(
        f"/admin/users/{user.id}/linked-sign-ins/{links[0].id}", headers=headers
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/users/{user.id}"
    assert await _state(users_app, user.id) == before
    async with users_app.state.sm.db.session_factory() as db:
        assert set((await db.execute(select(OAuthAccount.id))).scalars()) == {
            links[1].id,
            links[2].id,
        }
        audit = (
            await db.execute(
                select(AuditEntry).where(
                    AuditEntry.entity_type == "OAuthAccount",
                    AuditEntry.entity_id == str(links[0].id),
                    AuditEntry.action == "deleted",
                )
            )
        ).scalar_one()
        actor = (
            await db.execute(select(User).where(User.email == "admin@example.com"))
        ).scalar_one()
        assert audit.user_id == str(actor.id)
        assert "secret-access" not in str(audit.changes)
        assert "secret-refresh" not in str(audit.changes)
    page = await admin_client.get(response.headers["location"], headers={"X-Inertia": "true"})
    assert len(page.json()["props"]["linked_sign_ins"]) == 2
    assert page.json()["props"]["has_duplicate_linked_sign_ins"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("missing", ["owner", "link", "user"])
async def test_unlink_missing_or_not_owned_is_404(admin_client, users_db, linked_user, missing):
    user, links = linked_user
    headers = await _csrf(admin_client, user.id)
    uid, link_id = user.id, links[0].id
    if missing == "owner":
        uid = (await _make_user(users_db, "other@example.com")).id
    elif missing == "link":
        link_id = uuid.uuid4()
    else:
        uid = uuid.uuid4()
    response = await admin_client.delete(
        f"/admin/users/{uid}/linked-sign-ins/{link_id}", headers=headers
    )
    assert response.status_code == 404
    assert await users_db.get(OAuthAccount, links[0].id) is not None


@pytest.mark.anyio
@pytest.mark.parametrize("token", [None, "wrong"])
async def test_unlink_requires_csrf(admin_client, linked_user, token):
    user, links = linked_user
    await _csrf(admin_client, user.id)
    response = await admin_client.delete(
        f"/admin/users/{user.id}/linked-sign-ins/{links[0].id}",
        headers={"X-CSRF-Token": token} if token else {},
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_non_admin_cannot_unlink(user_client, linked_user):
    user, links = linked_user
    response = await user_client.delete(f"/admin/users/{user.id}/linked-sign-ins/{links[0].id}")
    assert response.status_code == 403


@pytest.mark.anyio
async def test_anonymous_cannot_unlink(anon_client, linked_user):
    user, links = linked_user
    response = await anon_client.delete(f"/admin/users/{user.id}/linked-sign-ins/{links[0].id}")
    assert response.status_code == 302
    assert response.headers["location"].startswith("/users/login")
