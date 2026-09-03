"""Changing your own password from the profile page.

fastapi-users' stock users router is not mounted, so ``/me`` only ever accepted
a display name. A password field on the profile needs an endpoint that proves
the caller knows the *current* password — a live session alone is not enough,
because a borrowed laptop is exactly the case this guards against.
"""

from __future__ import annotations

import pytest

_URL = "/api/users/me/password"
_ADMIN = {"username": "admin@example.com", "password": "AdminPass1!"}


async def _login(client, credentials: dict[str, str] | None = None) -> None:
    resp = await client.post("/api/users/auth/login", data=credentials or _ADMIN)
    assert resp.status_code == 204, resp.text


class TestChangePassword:
    @pytest.mark.anyio
    async def test_rejects_a_wrong_current_password(self, anon_client):
        await _login(anon_client)
        resp = await anon_client.post(
            _URL,
            json={"current_password": "NotMyPassword1!", "new_password": "BrandNewPass1!"},
        )
        assert resp.status_code == 400, resp.text

    @pytest.mark.anyio
    async def test_accepts_a_valid_change_and_the_new_password_works(self, anon_client):
        await _login(anon_client)
        resp = await anon_client.post(
            _URL,
            json={"current_password": "AdminPass1!", "new_password": "BrandNewPass1!"},
        )
        assert resp.status_code == 204, resp.text

        await _login(anon_client, {"username": "admin@example.com", "password": "BrandNewPass1!"})

    @pytest.mark.anyio
    async def test_enforces_the_password_policy_on_the_new_password(self, anon_client):
        await _login(anon_client)
        resp = await anon_client.post(
            _URL,
            json={"current_password": "AdminPass1!", "new_password": "1234567"},
        )
        assert resp.status_code == 400, resp.text

    @pytest.mark.anyio
    async def test_requires_authentication(self, anon_client):
        resp = await anon_client.post(
            _URL,
            json={"current_password": "AdminPass1!", "new_password": "BrandNewPass1!"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 401)

    @pytest.mark.anyio
    async def test_refuses_for_an_sso_account(self, anon_client, users_app, users_db):
        """An external user has no local password, so there is nothing to change."""
        from sqlalchemy import select
        from users.models import User

        await _login(anon_client)
        user = (
            await users_db.execute(select(User).where(User.email == "admin@example.com"))
        ).scalar_one()
        user.is_external = True
        await users_db.commit()

        resp = await anon_client.post(
            _URL,
            json={"current_password": "AdminPass1!", "new_password": "BrandNewPass1!"},
        )
        assert resp.status_code == 400, resp.text


class TestChangePasswordRevokesOtherSessions:
    """Changing a password is what you do when a session is in the wrong hands."""

    @pytest.mark.anyio
    async def test_another_browser_is_signed_out(self, anon_client, users_app):
        import httpx
        from simple_module_test import forge_session_cookie
        from sqlalchemy import select
        from users.models import User

        await _login(anon_client)
        async with users_app.state.sm.db.session_factory() as session:
            user_id = (
                await session.execute(select(User.id).where(User.email == "admin@example.com"))
            ).scalar_one()

        other = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=users_app),
            base_url="http://testserver",
            cookies={
                "session": forge_session_cookie(
                    str(users_app.state.sm.settings.secret_key),
                    {"user_id": str(user_id), "session_version": 0},
                )
            },
        )
        async with other:
            before = await other.get("/admin/users/", follow_redirects=False)
            assert before.status_code == 200, before.text

            resp = await anon_client.post(
                _URL,
                json={"current_password": "AdminPass1!", "new_password": "BrandNewPass1!"},
            )
            assert resp.status_code == 204, resp.text

            after = await other.get("/admin/users/", follow_redirects=False)
            assert after.status_code in (302, 401), after.text

    @pytest.mark.anyio
    async def test_the_changing_browser_keeps_working(self, anon_client):
        """Its session is re-stamped, so the bump does not catch the caller."""
        await _login(anon_client)
        resp = await anon_client.post(
            _URL,
            json={"current_password": "AdminPass1!", "new_password": "BrandNewPass1!"},
        )
        assert resp.status_code == 204, resp.text

        page = await anon_client.get("/admin/users/", follow_redirects=False)
        assert page.status_code == 200, page.text


class TestProfileProps:
    @pytest.mark.anyio
    async def test_profile_view_passes_the_real_user(self, admin_client):
        """The page read ``auth.user.full_name``, which has never existed."""
        resp = await admin_client.get(
            "/users/me", headers={"X-Inertia": "true", "Accept": "application/json"}
        )
        assert resp.status_code == 200, resp.text
        user = resp.json()["props"]["user"]
        assert user["email"] == "admin@example.com"
        assert user["full_name"] == "Test Admin"
        assert user["is_verified"] is True
        assert user["is_external"] is False


class TestChangePasswordIsRateLimited:
    """A live session plus a guessable current password is an online oracle.

    Wrong guesses cost nothing here — ``LoginRateLimiter`` only fronts
    ``/auth/login`` — so an attacker on an unattended browser could grind the
    current password at whatever rate the hasher allows.
    """

    @pytest.mark.anyio
    async def test_the_throughput_budget_applies(self, anon_client, users_app):
        from users.auth_local.rate_limit import ThroughputLimiter

        users_app.state.users.auth_throughput_limiter = ThroughputLimiter(
            max_attempts=2, window_seconds=60
        )
        await _login(anon_client)

        body = {"current_password": "NotMyPassword1!", "new_password": "BrandNewPass1!"}
        first = await anon_client.post(_URL, json=body)
        second = await anon_client.post(_URL, json=body)
        assert first.status_code == 400, first.text
        assert second.status_code == 400, second.text

        third = await anon_client.post(_URL, json=body)
        assert third.status_code == 429, third.text
