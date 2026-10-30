"""A mailbox password reset strands every previously issued credential (#686)."""

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlmodel import select
from users.models import RefreshToken, UserAccessToken
from users.session_revocation import CHANNEL


@pytest.mark.parametrize("credential", ["refresh", "session", "access"])
async def test_reset_revokes_old_credentials(admin_client, anon_client, users_app, credential):
    login = await anon_client.post(
        "/api/users/auth/login",
        data={"username": "admin@example.com", "password": "AdminPass1!"},
    )
    assert login.status_code == 204, login.text
    pair = await anon_client.post(
        "/api/users/auth/token",
        json={"email": "admin@example.com", "password": "AdminPass1!"},
    )
    assert pair.status_code == 200, pair.text
    tokens = pair.json()
    me = await anon_client.get("/api/users/me")
    assert me.status_code == 200, me.text
    # Warm the session-version cache before resetting in a separate client.
    assert (await anon_client.get("/admin/users/")).status_code == 200
    link = await admin_client.post(f"/api/users/admin/{me.json()['id']}/reset-password-link")
    assert link.status_code == 200, link.text
    token = parse_qs(urlsplit(link.json()["link"]).query)["token"][0]
    invalidations = []
    users_app.state.sm.invalidation.subscribe(CHANNEL, invalidations.append)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=users_app), base_url="http://testserver"
    ) as fresh:
        reset = await fresh.post(
            "/api/users/auth/reset-password",
            json={"token": token, "password": "NewCompliantPass1!"},
        )
        assert reset.status_code == 200, reset.text
        assert [message.key for message in invalidations] == [me.json()["id"]]
        async with users_app.state.sm.db.session_factory() as session:
            assert (await session.execute(select(UserAccessToken))).scalars().all() == []
            refresh_rows = (await session.execute(select(RefreshToken))).scalars().all()
            assert refresh_rows and all(row.revoked_at is not None for row in refresh_rows)
        if credential == "refresh":
            response = await fresh.post(
                "/api/users/auth/token/refresh", json={"refresh_token": tokens["refresh_token"]}
            )
            assert response.status_code == 401, response.text
        elif credential == "access":
            response = await fresh.get(
                "/api/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
            )
            assert response.status_code == 401, response.text
        else:
            response = await anon_client.get("/admin/users/", follow_redirects=False)
            assert response.status_code == 302, response.text
            assert "/users/login" in response.headers["location"]


async def test_reset_revokes_in_the_password_commit(
    admin_client, anon_client, users_app, monkeypatch
):
    """A failure after the password is stored must not leave old credentials valid."""
    from users.manager import UserManager

    pair = await anon_client.post(
        "/api/users/auth/token",
        json={"email": "admin@example.com", "password": "AdminPass1!"},
    )
    assert pair.status_code == 200, pair.text
    me = await anon_client.get(
        "/api/users/me", headers={"Authorization": f"Bearer {pair.json()['access_token']}"}
    )
    link = await admin_client.post(f"/api/users/admin/{me.json()['id']}/reset-password-link")
    token = parse_qs(urlsplit(link.json()["link"]).query)["token"][0]

    async def explode(self, user, request=None):
        raise RuntimeError("after-reset hook failed")

    monkeypatch.setattr(UserManager, "on_after_reset_password", explode)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=users_app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as fresh:
        reset = await fresh.post(
            "/api/users/auth/reset-password",
            json={"token": token, "password": "NewCompliantPass1!"},
        )
        assert reset.status_code == 500
        refreshed = await fresh.post(
            "/api/users/auth/token/refresh",
            json={"refresh_token": pair.json()["refresh_token"]},
        )
        assert refreshed.status_code == 401, refreshed.text
    async with users_app.state.sm.db.session_factory() as session:
        assert (await session.execute(select(UserAccessToken))).scalars().all() == []
