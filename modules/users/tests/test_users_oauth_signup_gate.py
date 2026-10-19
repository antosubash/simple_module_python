"""OAuth sign-in creates an account only when ``allow_signup`` is on (GH #543).

With signups closed, an operator who enables SSO for staff must not open a
signup to the provider's whole user base. Accounts that already exist — linked
by OAuth account or associated by email — still sign in.
"""

from __future__ import annotations

import uuid

import pytest
from _users_oauth_support import install_fake_provider, oauth_callback, set_allow_signup
from fastapi_users.password import PasswordHelper
from sqlalchemy import select
from users.models import User


async def _find(app, email: str) -> User | None:
    async with app.state.sm.db.session_factory() as session:
        stmt = select(User).where(User.email == email)
        return (await session.execute(stmt)).scalar_one_or_none()


@pytest.mark.anyio
async def test_signup_closed_refuses_a_new_identity(users_app, anon_client):
    install_fake_provider(users_app, "ms-new", "stranger@example.com")

    resp = await oauth_callback(anon_client)

    assert resp.status_code == 403
    assert resp.json()["detail"] == "OAUTH_SIGNUP_DISABLED"
    assert users_app.state.users.settings.cookie_name not in resp.cookies
    assert await _find(users_app, "stranger@example.com") is None


@pytest.mark.anyio
async def test_signup_open_creates_the_account(users_app, anon_client):
    set_allow_signup(users_app, True)
    install_fake_provider(users_app, "ms-new", "newcomer@example.com")

    assert (await oauth_callback(anon_client)).status_code == 303
    user = await _find(users_app, "newcomer@example.com")
    assert user is not None
    assert user.is_external is True


@pytest.mark.anyio
async def test_signup_closed_still_associates_an_existing_email(users_app, anon_client):
    async with users_app.state.sm.db.session_factory() as session:
        session.add(
            User(
                id=uuid.uuid4(),
                email="staff@example.com",
                hashed_password=PasswordHelper().hash("SecurePass1!"),
                is_active=True,
                is_verified=True,
            )
        )
        await session.commit()
    install_fake_provider(users_app, "ms-staff", "staff@example.com")

    assert (await oauth_callback(anon_client)).status_code == 303


@pytest.mark.anyio
async def test_signup_closed_still_signs_in_a_linked_oauth_account(users_app, anon_client):
    """Matched by the linked OAuth account even when the provider's email moved."""
    set_allow_signup(users_app, True)
    install_fake_provider(users_app, "ms-linked", "before@example.com")
    assert (await oauth_callback(anon_client)).status_code == 303

    set_allow_signup(users_app, False)
    anon_client.cookies.clear()
    install_fake_provider(users_app, "ms-linked", "after@example.com")

    assert (await oauth_callback(anon_client)).status_code == 303
    assert await _find(users_app, "after@example.com") is None
