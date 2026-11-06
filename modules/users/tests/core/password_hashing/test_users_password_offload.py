"""Crypto must run off-loop while the manager's DB operations stay on it."""

import asyncio
import os
import threading
import time
from unittest.mock import AsyncMock

import pytest
from fastapi_users import exceptions
from users.accounts.db_adapter import UserDatabaseWithRoles
from users.accounts.manager import UserManager
from users.admin.service import UserService
from users.contracts.schemas import UserCreate
from users.models import User


def build_manager(db, app):
    return UserManager(
        UserDatabaseWithRoles(db, User), app.state.users.mailer, app.state.users.settings
    )


@pytest.mark.parametrize("operation", ["create", "forgot", "reset", "update"])
async def test_crypto_runs_in_worker_thread(users_app, monkeypatch, operation):
    async with users_app.state.sm.db.session_factory() as db:
        manager = build_manager(db, users_app)
        user = await manager.get_by_email("admin@example.com")
        token = await manager.generate_reset_password_token(user)
        loop_thread = threading.get_ident()
        crypto_threads = []
        # Patch the class, not the shared ``PASSWORD_HELPER`` instance: undoing an
        # instance patch leaves a bound method in its ``__dict__`` that shadows
        # every later class-level patch (#860).
        helper_cls = type(manager.password_helper)
        for name in ("hash", "verify_and_update"):
            original = getattr(helper_cls, name)

            def record(self, *args, _original=original):
                crypto_threads.append(threading.get_ident())
                return _original(self, *args)

            monkeypatch.setattr(helper_cls, name, record)
        original_execute = db.execute

        async def execute(*args, **kwargs):
            assert threading.get_ident() == loop_thread
            return await original_execute(*args, **kwargs)

        monkeypatch.setattr(db, "execute", execute)
        if operation == "create":
            created = await manager.create(
                UserCreate(email="new@example.com", password="SecurePass1!", is_verified=True)
            )
            assert created.email == "new@example.com"
        elif operation == "forgot":
            manager.mailer.send_password_reset = AsyncMock()
            await manager.forgot_password(user)
            manager.mailer.send_password_reset.assert_awaited_once()
        elif operation == "reset":
            await manager.reset_password(token, "SecurePass1!")
            with pytest.raises(exceptions.InvalidResetPasswordToken):
                await manager.reset_password(token, "AnotherPass1!")
        else:
            await manager._update(user, {"password": "SecurePass1!"})
        assert crypto_threads
        assert loop_thread not in crypto_threads


def test_shared_helper_carries_no_instance_patches():
    """#860: tests must not leave instance attributes on the shared helper."""
    from users.core.password_hashing import PASSWORD_HELPER

    assert not {"hash", "verify_and_update"} & vars(PASSWORD_HELPER).keys()


async def test_managers_share_password_helper(users_app):
    async with users_app.state.sm.db.session_factory() as db:
        assert (
            build_manager(db, users_app).password_helper
            is build_manager(db, users_app).password_helper
        )


@pytest.mark.skipif(
    not os.getenv("SM_TEST_REAL_PASSWORD_HASHING"), reason="opt-in production-cost measurement"
)
@pytest.mark.parametrize("operation", ["bulk_invite", "forgot"])
async def test_real_hashing_loop_lag(users_app, operation):
    """A 5 ms heartbeat records worst scheduler delay across real service work."""
    delays = []
    running = True

    async def heartbeat():
        while running:
            started = time.perf_counter()
            await asyncio.sleep(0.005)  # intentional-sleep: heartbeat measuring loop lag
            delays.append(max(0, time.perf_counter() - started - 0.005))

    ticker = asyncio.create_task(heartbeat())
    await asyncio.sleep(0)
    started = time.perf_counter()
    try:
        async with users_app.state.sm.db.session_factory() as db:
            manager = build_manager(db, users_app)
            if operation == "bulk_invite":
                service = UserService(db, manager, users_app)
                for i in range(100):
                    await service.invite(f"lag-{i}@example.com", None, [])
            else:
                await manager.forgot_password(await manager.get_by_email("admin@example.com"))
    finally:
        running = False
        await ticker
    print(
        f"{operation}: elapsed={time.perf_counter() - started:.3f}s "
        f"max_loop_lag={max(delays) * 1000:.1f}ms"
    )
    assert max(delays) < 0.05


async def test_bearer_login_reuses_shared_helper(anon_client, monkeypatch):
    from fastapi_users.password import PasswordHelper

    def reject_construction(*args, **kwargs):
        raise AssertionError("request constructed another PasswordHelper")

    monkeypatch.setattr(PasswordHelper, "__init__", reject_construction)
    response = await anon_client.post(
        "/api/users/auth/token",
        json={"email": "admin@example.com", "password": "AdminPass1!"},
    )
    assert response.status_code == 200, response.text
