"""Transactional password changes, registration races and login scheduling."""

import asyncio
import threading
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi_users.exceptions import UserAlreadyExists
from fastapi_users.password import PasswordHelper
from simple_module_core.rate_limit import InProcessWindowStore
from simple_module_db import init_db
from sqlalchemy import func, select
from starlette.requests import Request
from users.accounts.db_adapter import UserDatabaseWithRoles
from users.accounts.manager import UserManager
from users.accounts.provider import UsersAuthProvider, clear_session_version_cache
from users.accounts.token_strategy import resolve_bearer
from users.auth_local import self_account
from users.auth_local.token_api import (
    RefreshRequest,
    TokenRequest,
    _create_token_pair,
    token_login,
    token_refresh,
)
from users.contracts.schemas import SelfPasswordChange, UserCreate
from users.core.settings import UsersSettings
from users.models import OAuthAccount, RefreshToken, User, UserAccessToken


@pytest.fixture
async def auth_database(tmp_path):
    state = init_db(f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")
    async with state.engine.begin() as connection:
        await connection.run_sync(User.metadata.create_all)
    config = UsersSettings(allow_signup=True)
    app = FastAPI()
    app.state.sm = SimpleNamespace(db=state, rate_limit_store=InProcessWindowStore())
    app.state.users = SimpleNamespace(settings=config, demo_user_ids=[])
    try:
        yield state, config, app
    finally:
        clear_session_version_cache()
        await state.engine.dispose()


def _manager(db, config, adapter=UserDatabaseWithRoles):
    return UserManager(adapter(db, User, OAuthAccount), SimpleNamespace(), config)


def _request(app):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/users/me/password",
            "headers": [],
            "query_string": b"",
            "session": {},
            "app": app,
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
        }
    )


@pytest.mark.parametrize("after_revoke", [False, True])
async def test_users_password_failure_rolls_back_hash_and_credentials(
    auth_database, monkeypatch, after_revoke
):
    state, config, app = auth_database
    helper = PasswordHelper()
    old_hash = await asyncio.to_thread(helper.hash, "OriginalPass1!")
    async with state.session_factory() as db:
        user = User(email="owner@example.com", is_verified=True, hashed_password=old_hash)
        db.add(user)
        await db.flush()
        user_id = user.id
        pair = await _create_token_pair(db, user.id, config)
        await db.commit()

    revoke = self_account.revoke_all_credentials

    async def fail(db, user, app):
        if after_revoke:
            await revoke(db, user, app)
        raise RuntimeError("injected revocation failure")

    monkeypatch.setattr(self_account, "revoke_all_credentials", fail)
    async with state.session_factory() as db:
        user = await db.get(User, user_id)
        with pytest.raises(RuntimeError, match="injected revocation"):
            await self_account.change_my_password(
                SelfPasswordChange(current_password="OriginalPass1!", new_password="NewPass1!"),
                _request(app),
                user,
                _manager(db, config),
                db,
                None,
            )
        await db.rollback()

    async with state.session_factory() as fresh:
        user = await fresh.get(User, user_id)
        assert user.hashed_password == old_hash
        assert user.session_version == 0
        assert await fresh.scalar(select(func.count()).select_from(UserAccessToken)) == 1
        refresh = await fresh.scalar(select(RefreshToken))
        assert refresh.revoked_at is None
    assert await UsersAuthProvider()._version_still_current(
        {"app": app}, user_id, {"session_version": 0}
    )
    assert await resolve_bearer({"app": app}, pair.access_token) is not None
    async with state.session_factory() as fresh:
        refreshed = await token_refresh(
            RefreshRequest(refresh_token=pair.refresh_token), _request(app), db=fresh
        )
        assert refreshed.access_token


async def test_users_concurrent_case_variant_signup_has_one_winner(auth_database):
    state, config, _ = auth_database
    barrier = asyncio.Barrier(2)

    class GatedAdapter(UserDatabaseWithRoles):
        async def get_by_email(self, email):
            found = await super().get_by_email(email)
            if not getattr(self, "checked", False):
                self.checked = True
                await asyncio.wait_for(barrier.wait(), timeout=10)
            return found

    async def signup(email):
        async with state.session_factory() as db:
            return await _manager(db, config, GatedAdapter).create(
                UserCreate(email=email, password="ValidPassword1!", is_verified=True)
            )

    results = await asyncio.gather(
        signup("Alice@example.com"), signup("alice@example.com"), return_exceptions=True
    )
    assert sum(isinstance(result, User) for result in results) == 1, results
    assert sum(isinstance(result, UserAlreadyExists) for result in results) == 1, results
    async with state.session_factory() as fresh:
        assert await fresh.scalar(select(func.count()).select_from(User)) == 1
        user = await UserDatabaseWithRoles(fresh, User, OAuthAccount).get_by_email(
            "ALICE@example.com"
        )
        assert user.email == "alice@example.com"


@pytest.mark.parametrize("path", ["manager", "token"])
@pytest.mark.parametrize("account", ["missing", "external", "local"])
async def test_users_login_password_work_runs_off_loop(auth_database, monkeypatch, path, account):
    state, config, app = auth_database
    if account != "missing":
        async with state.session_factory() as db:
            db.add(
                User(
                    email="owner@example.com",
                    hashed_password="hash" if account == "local" else None,
                )
            )
            await db.commit()
    loop_thread = threading.get_ident()
    threads = []

    def hash_password(self, password):
        threads.append(threading.get_ident())
        return "dummy"

    def verify(self, password, hashed):
        threads.append(threading.get_ident())
        return False, None

    monkeypatch.setattr(PasswordHelper, "hash", hash_password)
    monkeypatch.setattr(PasswordHelper, "verify_and_update", verify)
    async with state.session_factory() as db:
        if path == "manager":
            result = await _manager(db, config).authenticate(
                SimpleNamespace(username="owner@example.com", password="Incorrect1!")
            )
            assert result is None
        else:
            with pytest.raises(HTTPException) as error:
                await token_login(
                    TokenRequest(email="owner@example.com", password="Incorrect1!"),
                    _request(app),
                    db=db,
                )
            assert error.value.status_code == 401
    assert threads and all(thread != loop_thread for thread in threads)


async def test_users_registration_normalizes_and_rejects_sequential_duplicate(auth_database):
    state, config, _ = auth_database
    async with state.session_factory() as db:
        created = await _manager(db, config).create(
            UserCreate(email="Alice@example.com", password="ValidPassword1!", is_verified=True)
        )
        assert created.email == "alice@example.com"
    async with state.session_factory() as db:
        with pytest.raises(UserAlreadyExists):
            await _manager(db, config).create(
                UserCreate(email="ALICE@example.com", password="ValidPassword1!")
            )


async def test_users_registration_preserves_unrelated_integrity_errors(auth_database):
    from sqlalchemy.exc import IntegrityError

    state, _, _ = auth_database
    async with state.session_factory() as db:
        user = User(email="owner@example.com")
        db.add(user)
        await db.commit()
        user_id = user.id
    async with state.session_factory() as db:
        adapter = UserDatabaseWithRoles(db, User, OAuthAccount)
        with pytest.raises(IntegrityError):
            await adapter.create({"id": user_id, "email": "other@example.com"})
        # The losing insert does not leave the session unusable.
        assert await adapter.get_by_email("owner@example.com") is not None


async def test_users_password_change_preserves_update_hook(auth_database, monkeypatch):
    state, config, app = auth_database
    async with state.session_factory() as db:
        manager = _manager(db, config)
        user = User(
            email="owner@example.com",
            hashed_password=manager.password_helper.hash("OriginalPass1!"),
        )
        db.add(user)
        await db.commit()
        observed = []

        async def after_update(updated, changes, request):
            observed.append((updated.id, changes, request.app))

        monkeypatch.setattr(manager, "on_after_update", after_update)
        response = await self_account.change_my_password(
            SelfPasswordChange(current_password="OriginalPass1!", new_password="ReplacementPass1!"),
            _request(app),
            user,
            manager,
            db,
            None,
        )
        assert response.status_code == 204
        assert observed == [(user.id, {"password": "ReplacementPass1!"}, app)]
