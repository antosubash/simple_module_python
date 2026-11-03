"""Races the unique lower(email) index has to resolve cleanly (#731 review)."""

from __future__ import annotations

import pytest
from fastapi_users.exceptions import UserAlreadyExists
from simple_module_db.callbacks import register_on_commit, run_on_commit_callbacks
from test_service_admin import _build_service


@pytest.mark.anyio
async def test_lost_create_race_keeps_other_pending_commit_work(users_app):
    from users.db_adapter import UserDatabaseWithRoles
    from users.models import User

    ran = []
    async with users_app.state.sm.db.session_factory() as session:
        db = UserDatabaseWithRoles(session, User)
        await db.create({"email": "first@example.com", "hashed_password": "x"})
        # Queued for another account in the same request (a bulk invite).
        register_on_commit(session, lambda: ran.append("invite mail"))
        with pytest.raises(UserAlreadyExists):
            await db.create({"email": "FIRST@example.com", "hashed_password": "x"})
        await session.commit()
        await run_on_commit_callbacks(session)
    assert ran == ["invite mail"]


@pytest.mark.anyio
async def test_admin_email_edit_is_stored_lowercase(users_app):
    from test_api_admin import _make_user

    async with users_app.state.sm.db.session_factory() as session:
        user = await _make_user(session, email="edit-me@example.com")
        svc = _build_service(session, users_app)
        updated = await svc.update_details(user.id, email="Edit.Me@Example.com", full_name=None)
        assert updated.email == "edit.me@example.com"


@pytest.mark.anyio
async def test_admin_email_edit_race_is_a_duplicate_error(users_app, monkeypatch):
    from test_api_admin import _make_user
    from users.exceptions import EmailAlreadyExistsError

    async with users_app.state.sm.db.session_factory() as session:
        await _make_user(session, email="taken@example.com")
        target = await _make_user(session, email="mover@example.com")
        svc = _build_service(session, users_app)
        # The other account appears after the pre-check, as in a concurrent signup.
        execute = session.execute

        class _NoClash:
            def scalar_one_or_none(self):
                return None

        async def precheck_misses(statement, *args, **kwargs):
            if "lower(" in str(statement):
                monkeypatch.setattr(session, "execute", execute)
                return _NoClash()
            return await execute(statement, *args, **kwargs)

        monkeypatch.setattr(session, "execute", precheck_misses)
        with pytest.raises(EmailAlreadyExistsError):
            await svc.update_details(target.id, email="TAKEN@example.com", full_name=None)


@pytest.mark.anyio
async def test_create_admin_stores_email_lowercase(users_app):
    from users.bootstrap import create_admin

    async with users_app.state.sm.db.session_factory() as session:
        result = await create_admin(
            session, email="Boot.Admin@Example.com", password="SecurePass1!"
        )
        assert result.user.email == "boot.admin@example.com"
