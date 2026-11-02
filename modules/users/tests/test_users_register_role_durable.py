"""The signup role survives a failure later in registration (GH #488 review).

fastapi-users commits the user row inside ``create()``, before
``on_after_register``. A role that was only flushed was rolled back when the
verification email then failed, leaving a committed account with no role that
could not re-register either.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from simple_module_hosting.settings import Settings
from sqlalchemy import select

EMAIL = "mailfail@example.com"


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"multi_tenant": False, "tenant_header": ""})


async def test_role_is_kept_when_the_verification_email_fails(app, client):
    from users.bootstrap import ensure_user_role
    from users.constants import USER_ROLE_NAME
    from users.models import Role, User, UserRole

    async with app.state.sm.db.session_factory() as session:
        await ensure_user_role(session)
        await session.commit()
    users = app.state.users
    users.settings = users.settings.model_copy(
        update={"allow_signup": True, "require_verification": True}
    )
    users.mailer.send_verification = AsyncMock(side_effect=ConnectionError("SMTP down"))

    try:
        resp = await client.post(
            "/api/users/auth/register", json={"email": EMAIL, "password": "SecurePass1!"}
        )
        assert resp.status_code >= 500
    except ConnectionError:
        pass  # the transport re-raised the app's exception: the same failure

    async with app.state.sm.db.session_factory() as session:
        user = (await session.execute(select(User).where(User.email == EMAIL))).scalar_one()
        names = (
            await session.execute(
                select(Role.name).join(UserRole).where(UserRole.user_id == user.id)
            )
        ).scalars()
        assert list(names) == [USER_ROLE_NAME]
