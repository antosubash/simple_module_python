"""What "Keep me signed in for 30 days" actually extends.

The checkbox is only honest if every part of the credential outlives the
promise. Three things expire independently: the Starlette session cookie the
pages authenticate with, the ``sm_auth`` cookie, and the access-token row
behind it. Whichever runs out first is the real answer, so all three are
pinned here.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi_users.password import PasswordHelper
from users.models import User

_pw = PasswordHelper()

_INERTIA_HEADERS = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}
REMEMBER_ME_MAX_AGE = 30 * 24 * 60 * 60


async def _make_user(session, email: str, password: str = "SecurePass1!") -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=_pw.hash(password),
        is_active=True,
        is_superuser=False,
        is_verified=True,
        full_name="Test User",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _set_cookie(resp, name: str) -> str:
    """Return the raw ``Set-Cookie`` header for *name* (httpx drops attributes)."""
    headers = [v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"]
    matching = [h for h in headers if h.startswith(f"{name}=")]
    assert matching, f"no Set-Cookie for {name!r} in {headers!r}"
    return matching[-1]


async def _login(client, email: str, *, remember: bool | None = None):
    data = {"username": email, "password": "SecurePass1!"}
    if remember is not None:
        data["remember"] = str(remember).lower()
    return await client.post("/api/users/auth/login", data=data)


async def _age_access_tokens(app, *, days: int) -> None:
    """Backdate every access-token row — fastapi-users compares ``created_at``
    against the strategy's lifetime, so this is how the window is observable
    without waiting a month."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update
    from users.models import UserAccessToken

    async with app.state.sm.db.session_factory() as session:
        await session.execute(
            update(UserAccessToken).values(
                created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
            )
        )
        await session.commit()


class TestRemembered:
    @pytest.mark.anyio
    async def test_the_auth_cookie_lasts_thirty_days(self, anon_client, users_db):
        await _make_user(users_db, "remember@example.com")
        resp = await _login(anon_client, "remember@example.com", remember=True)
        assert resp.status_code == 204, resp.text
        assert f"Max-Age={REMEMBER_ME_MAX_AGE}" in _set_cookie(resp, "sm_auth")

    @pytest.mark.anyio
    async def test_the_session_cookie_lasts_thirty_days(self, anon_client, users_db):
        """The one that actually keeps the browser signed in: page auth reads
        the Starlette session, not ``sm_auth``."""
        await _make_user(users_db, "remember-session@example.com")
        resp = await _login(anon_client, "remember-session@example.com", remember=True)
        assert resp.status_code == 204, resp.text
        assert f"Max-Age={REMEMBER_ME_MAX_AGE}" in _set_cookie(resp, "session")

    @pytest.mark.anyio
    async def test_a_token_inside_the_promised_window_is_still_read(
        self, anon_client, users_db, users_app
    ):
        """The write window is worthless if the read window is shorter.

        ``current_user`` resolves one strategy for every request, so it cannot
        know which sign-ins asked to be remembered — a row minted to last
        thirty days therefore has to be accepted for thirty, or the cookie
        outlives the credential it carries and the checkbox starts lying on
        day fourteen. ``/api/users/me`` is the probe because it depends on
        ``current_user``, which is the code path that reads the row.
        """
        await _make_user(users_db, "remember-token@example.com")
        await _login(anon_client, "remember-token@example.com", remember=True)

        await _age_access_tokens(users_app, days=29)
        assert (await anon_client.get("/api/users/me")).status_code == 200

    @pytest.mark.anyio
    async def test_a_token_past_the_window_stops_being_read(self, anon_client, users_db, users_app):
        """The other end of the same window — without this the test above
        would pass against an unbounded lifetime."""
        await _make_user(users_db, "stale-token@example.com")
        await _login(anon_client, "stale-token@example.com", remember=True)

        await _age_access_tokens(users_app, days=31)
        assert (await anon_client.get("/api/users/me")).status_code == 401


class TestNotRemembered:
    @pytest.mark.anyio
    async def test_the_auth_cookie_keeps_the_configured_default(
        self, anon_client, users_db, users_app
    ):
        await _make_user(users_db, "plain@example.com")
        resp = await _login(anon_client, "plain@example.com")
        assert resp.status_code == 204, resp.text
        default = users_app.state.users.settings.cookie_max_age_seconds
        assert f"Max-Age={default}" in _set_cookie(resp, "sm_auth")

    @pytest.mark.anyio
    async def test_the_session_cookie_keeps_the_fourteen_day_default(self, anon_client, users_db):
        await _make_user(users_db, "plain-session@example.com")
        resp = await _login(anon_client, "plain-session@example.com")
        assert resp.status_code == 204, resp.text
        assert "Max-Age=1209600" in _set_cookie(resp, "session")


@pytest.mark.anyio
async def test_the_login_page_states_the_window_it_will_honour(anon_client):
    resp = await anon_client.get("/users/login", headers=_INERTIA_HEADERS)
    assert resp.json()["props"]["remember_me_days"] == 30
