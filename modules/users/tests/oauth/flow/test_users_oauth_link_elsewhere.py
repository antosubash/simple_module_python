"""Verified email can add a provider, but cannot replace its identity (#1128)."""

import logging

import pytest
from _users_microsoft_support import OID, install_microsoft
from _users_oauth_support import install_fake_provider, oauth_callback, seed_password_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from users.models import OAuthAccount, Role, User, UserRole

_EMAIL = "jane@corp.com"
_OTHER_OID = "2b2c3d4e-5f60-4a7b-8c9d-0e1f2a3b4c5d"


async def _account_state(app):
    async with app.state.sm.db.session_factory() as session:
        user = (
            await session.execute(
                select(User).where(User.email == _EMAIL).options(selectinload(User.roles))
            )
        ).scalar_one()
        links = {
            (link.oauth_name, link.account_id): (link.access_token, link.last_sign_in_at)
            for link in (await session.execute(select(OAuthAccount))).scalars()
        }
        return user.id, {role.name for role in user.roles}, links


@pytest.fixture
async def local_account(users_app):
    user_id = await seed_password_user(users_app, _EMAIL, is_verified=True)
    async with users_app.state.sm.db.session_factory() as session:
        role = Role(name="oauth-test-role")
        session.add(role)
        await session.flush()
        session.add(UserRole(user_id=user_id, role_id=role.id))
        await session.commit()
    return user_id


@pytest.mark.anyio
@pytest.mark.parametrize("browser", [True, False])
async def test_second_microsoft_identity_is_refused(
    users_app, anon_client, local_account, caplog, browser
):
    install_microsoft(users_app)
    assert (await oauth_callback(anon_client, "microsoft")).status_code == 303
    before = await _account_state(users_app)
    assert before[:2] == (local_account, {"oauth-test-role"})
    assert set(before[2]) == {("microsoft", OID)}
    anon_client.cookies.clear()
    anon_client.headers["accept"] = "text/html" if browser else "application/json"
    install_microsoft(users_app, oid=_OTHER_OID)

    response = await oauth_callback(anon_client, "microsoft")

    if browser:
        assert response.status_code == 303
        assert response.headers["location"] == "/users/login?oauth_error=account_linked_elsewhere"
        page = await anon_client.get(response.headers["location"], headers={"X-Inertia": "true"})
        assert page.status_code == 200
        assert page.json()["props"]["oauth_error"] == "account_linked_elsewhere"
    else:
        assert response.status_code == 403
        assert response.json()["detail"] == "OAUTH_ACCOUNT_LINKED_ELSEWHERE"
    assert users_app.state.users.settings.cookie_name not in response.cookies
    assert await _account_state(users_app) == before

    warning = next(
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "OAUTH_ACCOUNT_LINKED_ELSEWHERE" in r.getMessage()
    )
    assert warning.getMessage() == (
        "OAuth sign-in through microsoft refused: "
        f"OAUTH_ACCOUNT_LINKED_ELSEWHERE (user {local_account})"
    )


@pytest.mark.anyio
async def test_first_link_repeat_signin_and_different_provider(
    users_app, anon_client, local_account
):
    install_microsoft(users_app)
    for _ in range(2):
        response = await oauth_callback(anon_client, "microsoft")
        assert response.status_code == 303
        assert users_app.state.users.settings.cookie_name in response.cookies
        anon_client.cookies.clear()

    install_fake_provider(users_app, "other-provider-id", _EMAIL)
    response = await oauth_callback(anon_client)
    assert response.status_code == 303
    assert users_app.state.users.settings.cookie_name in response.cookies
    user_id, roles, links = await _account_state(users_app)
    assert user_id == local_account
    assert roles == {"oauth-test-role"}
    assert set(links) == {("microsoft", OID), ("oidc", "other-provider-id")}


@pytest.mark.anyio
async def test_unverified_microsoft_identity_cannot_link(users_app, anon_client, local_account):
    install_microsoft(users_app, trust=False)

    response = await oauth_callback(anon_client, "microsoft")

    assert response.status_code == 400
    assert response.json()["detail"] == "OAUTH_USER_ALREADY_EXISTS"
    assert await _account_state(users_app) == (local_account, {"oauth-test-role"}, {})


@pytest.mark.anyio
async def test_admin_unlink_allows_new_verified_identity(
    users_app, anon_client, admin_client, local_account
):
    install_microsoft(users_app)
    assert (await oauth_callback(anon_client, "microsoft")).status_code == 303
    anon_client.cookies.clear()
    install_microsoft(users_app, oid=_OTHER_OID)
    assert (await oauth_callback(anon_client, "microsoft")).status_code == 403
    anon_client.cookies.clear()

    async with users_app.state.sm.db.session_factory() as db:
        link = (await db.execute(select(OAuthAccount))).scalar_one()
        link_id = link.id
    page = await admin_client.get(f"/admin/users/{local_account}", headers={"X-Inertia": "true"})
    response = await admin_client.delete(
        f"/admin/users/{local_account}/linked-sign-ins/{link_id}",
        headers={"X-CSRF-Token": page.json()["props"]["csrfToken"]},
    )
    assert response.status_code == 303
    assert await _account_state(users_app) == (local_account, {"oauth-test-role"}, {})

    response = await oauth_callback(anon_client, "microsoft")
    assert response.status_code == 303
    assert users_app.state.users.settings.cookie_name in response.cookies
    user_id, roles, links = await _account_state(users_app)
    assert (user_id, roles) == (local_account, {"oauth-test-role"})
    assert set(links) == {("microsoft", _OTHER_OID)}
