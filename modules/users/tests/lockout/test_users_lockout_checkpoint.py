"""Checkpoint isolation on file SQLite, where overlapping writers cannot hide."""

from datetime import UTC, datetime

import pytest
from _users_app_builders import ALICE, _build_users_app, _client, _make_standard_user, user_row
from pwdlib.hashers.bcrypt import BcryptHasher
from simple_module_core.rate_limit import InProcessWindowStore
from sqlalchemy import select
from users.auth_local.lockout import LoginAttempt, admit
from users.models import Role, User


@pytest.fixture
async def checkpoint_app(monkeypatch, tmp_path):
    app, context = await _build_users_app(
        monkeypatch,
        allow_signup=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'auth-checkpoint.db'}",
    )
    await _make_standard_user(app, ALICE)
    try:
        yield app
    finally:
        await context.__aexit__(None, None, None)


async def test_admission_never_flushes_or_commits_unrelated_request_work(checkpoint_app):
    observed = []
    factory = checkpoint_app.state.sm.db.session_factory
    attempt = LoginAttempt.build(
        ALICE,
        "1.2.3.4",
        InProcessWindowStore(),
        checkpoint_app.state.users.settings,
        datetime.now(UTC),
    )
    async with factory() as request:
        pending = Role(name="pending-request-role")
        request.add(pending)
        request.on_commit(lambda: observed.append("request"))
        admission = await admit(request, attempt)
        assert admission.count == 1
        assert pending in request.new
        assert observed == []
        await request.rollback()
    assert (await user_row(checkpoint_app, ALICE)).failed_login_count == 1
    async with factory() as reader:
        assert (
            await reader.execute(select(Role).where(Role.name == "pending-request-role"))
        ).scalar_one_or_none() is None


async def test_unverified_legacy_password_releases_slot_without_overlapping_writers(checkpoint_app):
    factory = checkpoint_app.state.sm.db.session_factory
    async with factory() as session:
        user = (await session.execute(select(User).where(User.email == ALICE))).scalar_one()
        user.is_verified = False
        user.hashed_password = BcryptHasher(rounds=4).hash("UserPass1!")
        await session.commit()
    checkpoint_app.state.users.settings = checkpoint_app.state.users.settings.model_copy(
        update={"require_verification": True}
    )
    async with _client(checkpoint_app, "1.2.3.4") as client:
        response = await client.post(
            "/api/users/auth/token", json={"email": ALICE, "password": "UserPass1!"}
        )
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "LOGIN_USER_NOT_VERIFIED"
    assert (await user_row(checkpoint_app, ALICE)).failed_login_count == 0


@pytest.mark.parametrize("kind", ["cookie", "token"])
async def test_unverified_logins_release_request_connections_before_checkpoint(
    checkpoint_app, monkeypatch, kind
):
    import asyncio

    from users.auth_local import api, token_api

    # SQLite's default pool has five connections plus ten overflow connections.
    emails = [f"unverified-{i}@example.com" for i in range(15)]
    for email in emails:
        await _make_standard_user(checkpoint_app, email)
    async with checkpoint_app.state.sm.db.session_factory() as session:
        for user in (await session.execute(select(User).where(User.email.in_(emails)))).scalars():
            user.is_verified = False
        await session.commit()
    checkpoint_app.state.users.settings = checkpoint_app.state.users.settings.model_copy(
        update={"require_verification": True}
    )
    endpoint = api if kind == "cookie" else token_api
    real_release = endpoint.release
    ready = asyncio.Barrier(len(emails))

    async def together(session, attempt, admission):
        await ready.wait()
        return await real_release(session, attempt, admission)

    monkeypatch.setattr(endpoint, "release", together)

    async def login(email):
        async with _client(checkpoint_app, "1.2.3.4") as client:
            if kind == "cookie":
                return await client.post(
                    "/api/users/auth/login", data={"username": email, "password": "UserPass1!"}
                )
            return await client.post(
                "/api/users/auth/token", json={"email": email, "password": "UserPass1!"}
            )

    responses = await asyncio.wait_for(asyncio.gather(*(login(email) for email in emails)), 5)
    assert [response.status_code for response in responses] == [400] * 15
    assert all(response.json()["detail"] == "LOGIN_USER_NOT_VERIFIED" for response in responses)
