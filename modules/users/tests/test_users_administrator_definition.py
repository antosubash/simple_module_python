"""Setup and account writes agree on active administrators."""

from datetime import UTC, datetime

import pytest
from simple_module_test.setup_wizard import wizard_client, wizard_headers
from sqlalchemy import select
from users.admin.service import UserService
from users.administrators import count_active_administrators
from users.bootstrap import ensure_admin_role
from users.exceptions import AdminAccountSafetyError
from users.models import User, UserRole
from users.setup import STEP_ADMINISTRATOR, has_local_account


async def test_role_administrator_keeps_setup_complete_after_superuser_disabled(setup_pending_app):
    app = setup_pending_app
    async with wizard_client(app) as client:
        headers = await wizard_headers(client)
        async with app.state.sm.db.session_factory() as session:
            role = await ensure_admin_role(session)
            superuser = User(email="super@example.com", hashed_password="unused", is_superuser=True)
            administrator = User(email="role@example.com", hashed_password="unused")
            session.add_all([superuser, administrator])
            await session.flush()
            session.add(UserRole(user_id=administrator.id, role_id=role.id))
            await session.commit()
            await UserService(session, None, app).disable(superuser.id)
            await session.commit()
        async with app.state.sm.db.session_factory() as session:
            assert await count_active_administrators(session) == 1
        response = await client.post(
            f"/setup/steps/{STEP_ADMINISTRATOR}",
            json={"email": "new@example.com", "password": "SetupPass1!"},
            headers=headers,
        )
        assert response.status_code in (404, 409)
        assert (await client.get("/setup")).status_code == 404
        assert (await client.get("/", follow_redirects=False)).headers.get("location") != "/setup"


@pytest.mark.parametrize("disabled", [False, True])
async def test_existing_user_closes_the_first_administrator_action(setup_pending_app, disabled):
    """Once any account exists the anonymous action is never offered again."""
    async with wizard_client(setup_pending_app) as client:
        headers = await wizard_headers(client)  # open while the table is empty
        async with setup_pending_app.state.sm.db.session_factory() as session:
            session.add(
                User(
                    email="existing@example.com",
                    hashed_password="unused",
                    is_active=not disabled,
                    disabled_at=datetime.now(UTC) if disabled else None,
                )
            )
            await session.commit()
        response = await client.post(
            f"/setup/steps/{STEP_ADMINISTRATOR}",
            json={"email": "new@example.com", "password": "SetupPass1!"},
            headers=headers,
        )
    assert response.status_code in (404, 409)
    async with setup_pending_app.state.sm.db.session_factory() as session:
        assert list(await session.scalars(select(User.email))) == ["existing@example.com"]


@pytest.mark.parametrize(
    "kind,operation",
    [
        ("superuser", "disable"),
        ("superuser", "delete"),
        ("role", "disable"),
        ("role", "delete"),
        ("role", "demote"),
        ("both", "disable"),
        ("both", "delete"),
        ("both", "demote"),
    ],
)
async def test_last_active_administrator_is_preserved(setup_pending_app, kind, operation):
    app = setup_pending_app
    async with app.state.sm.db.session_factory() as session:
        user = User(
            email="admin@example.com", hashed_password="unused", is_superuser=kind != "role"
        )
        session.add(user)
        await session.flush()
        if kind != "superuser":
            role = await ensure_admin_role(session)
            session.add(UserRole(user_id=user.id, role_id=role.id))
        await session.commit()
        # Permissions resolve from roles: a roleless superuser is not an administrator.
        assert (await count_active_administrators(session) > 0) is (kind != "superuser")
        service = UserService(session, None, app)
        with pytest.raises(AdminAccountSafetyError):
            if operation == "demote":
                await service.set_roles(user.id, [])
            elif operation == "delete":
                await service.delete_user(user.id)
            else:
                await service.disable(user.id)


@pytest.mark.parametrize(
    "is_active,disabled_at", [(False, None), (True, datetime(2026, 1, 1, tzinfo=UTC))]
)
async def test_unavailable_superuser_is_not_an_active_administrator(
    setup_pending_app, is_active, disabled_at
):
    async with setup_pending_app.state.sm.db.session_factory() as session:
        session.add(
            User(
                email="inactive@example.com",
                hashed_password="unused",
                is_superuser=True,
                is_active=is_active,
                disabled_at=disabled_at,
            )
        )
        await session.commit()
        assert await count_active_administrators(session) == 0


async def test_roleless_superuser_is_not_a_surviving_administrator(setup_pending_app):
    """``is_superuser`` grants no permissions, so it cannot stand in for the last admin."""
    app = setup_pending_app
    async with app.state.sm.db.session_factory() as session:
        role = await ensure_admin_role(session)
        administrator = User(email="role@example.com", hashed_password="unused")
        superuser = User(email="super@example.com", hashed_password="unused", is_superuser=True)
        session.add_all([administrator, superuser])
        await session.flush()
        session.add(UserRole(user_id=administrator.id, role_id=role.id))
        await session.commit()
        with pytest.raises(AdminAccountSafetyError):
            await UserService(session, None, app).disable(administrator.id)


async def test_install_with_accounts_but_no_administrator_is_not_gated(setup_pending_app):
    """Accounts without an administrator recover via the CLI, not a wizard that refuses."""
    app = setup_pending_app
    async with app.state.sm.db.session_factory() as session:
        session.add(User(email="member@example.com", hashed_password="unused"))
        await session.commit()
        assert await count_active_administrators(session) == 0
    assert await has_local_account(app) is True
    async with wizard_client(app) as client:
        assert (await client.get("/setup")).status_code == 404
