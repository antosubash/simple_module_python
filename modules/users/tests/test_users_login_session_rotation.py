"""Signing in must discard pre-login state and refresh Inertia's CSRF prop."""

import pytest
from _users_oauth_support import install_fake_provider, oauth_callback, seed_password_user
from fastapi import Depends, Request
from simple_module_hosting.csrf import CSRF_HEADER, RequiresCsrf, get_csrf_token

_INERTIA = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}
_PROBE = "/api/users/auth/rotation-probe"


def _install_probe(app):
    @app.get(_PROBE)
    async def seed(request: Request):
        request.session["untrusted"] = "discard me"
        return {"token": get_csrf_token(request)}

    @app.post(_PROBE, dependencies=[Depends(RequiresCsrf())])
    async def mutation():
        return {"ok": True}

    @app.get(f"{_PROBE}/session")
    async def session(request: Request):
        return dict(request.session)


async def _assert_rotated(client, old):
    # Reload the page through Inertia as Login.tsx's router.visit does.
    page = await client.get("/users/login", headers=_INERTIA)
    assert page.status_code == 200, page.text
    new = page.json()["props"]["csrfToken"]
    assert new != old
    assert (await client.post(_PROBE, headers={CSRF_HEADER: old})).status_code == 403
    assert (await client.post(_PROBE, headers={CSRF_HEADER: new})).status_code == 200
    session = (await client.get(f"{_PROBE}/session")).json()
    assert "untrusted" not in session
    assert "session_version" in session
    assert "expires_at" in session
    assert "is_demo" not in session
    return new


@pytest.mark.parametrize("method", ["password", "oauth", "invite"])
async def test_sign_in_rotates_session_and_page_token(users_app, anon_client, method):
    _install_probe(users_app)
    old = (await anon_client.get(_PROBE)).json()["token"]
    anon_client.cookies.set("locale", "en")
    if method == "password":
        response = await anon_client.post(
            "/api/users/auth/login",
            data={"username": "admin@example.com", "password": "AdminPass1!"},
        )
        assert response.status_code == 204, response.text
    elif method == "oauth":
        await seed_password_user(users_app, "oauth@example.com", is_verified=True)
        install_fake_provider(users_app, "ms-rotation", "oauth@example.com")
        # AuthMiddleware supplies the return target, not the test route.
        await anon_client.get("/admin/users/?page=2", follow_redirects=False)
        response = await oauth_callback(anon_client)
        assert response.status_code == 303, response.text
        assert response.headers["location"] == "/admin/users/?page=2"
    else:
        from users.db_adapter import UserDatabaseWithRoles
        from users.manager import UserManager
        from users.models import User

        await seed_password_user(users_app, "invite@example.com", is_verified=False)
        async with users_app.state.sm.db.session_factory() as db:
            adapter = UserDatabaseWithRoles(db, User)
            user = await adapter.get_by_email("invite@example.com")
            manager = UserManager(adapter, None, users_app.state.users.settings)
            token = manager.mint_invite_token(user)
        response = await anon_client.post(
            "/api/users/auth/accept-invite", json={"token": token, "password": "NewSecurePass1!"}
        )
        assert response.status_code == 204, response.text
    await _assert_rotated(anon_client, old)
    session = (await anon_client.get(f"{_PROBE}/session")).json()
    assert "next" not in session
    assert anon_client.cookies.get("locale") == "en"


async def test_switching_users_discards_previous_context(users_app, anon_client):
    _install_probe(users_app)
    await seed_password_user(users_app, "second@example.com", is_verified=True)
    assert (
        await anon_client.post(
            "/api/users/auth/login",
            data={"username": "admin@example.com", "password": "AdminPass1!", "remember": "true"},
        )
    ).status_code == 204
    old = (await anon_client.get("/users/login", headers=_INERTIA)).json()["props"]["csrfToken"]
    assert (
        await anon_client.post(
            "/api/users/auth/login",
            data={"username": "second@example.com", "password": "SecurePass1!"},
        )
    ).status_code == 204
    await _assert_rotated(anon_client, old)
    session = (await anon_client.get(f"{_PROBE}/session")).json()
    assert "remember" not in session
    assert (await anon_client.get("/api/users/me")).json()["email"] == "second@example.com"


async def test_demo_sign_in_rotates_token_and_restamps_marker(demo_app, demo_client):
    _install_probe(demo_app)
    old = (await demo_client.get(_PROBE)).json()["token"]
    assert (await demo_client.post("/api/users/auth/demo/user")).status_code == 204
    props = (await demo_client.get("/users/login", headers=_INERTIA)).json()["props"]
    assert props["csrfToken"] != old
    assert props["demo"]["active"] is True
    session = (await demo_client.get(f"{_PROBE}/session")).json()
    assert "untrusted" not in session


async def test_registered_gate_keys_survive_sign_in(users_app, anon_client):
    from simple_module_hosting.session import preserve_across_sign_in

    preserve_across_sign_in(users_app, "gate_marker")

    @users_app.get(f"{_PROBE}/gate")
    async def gate(request: Request):
        request.session["gate_marker"] = "unlocked"
        request.session["untrusted"] = "discard me"
        return {}

    _install_probe(users_app)
    await anon_client.get(f"{_PROBE}/gate")
    response = await anon_client.post(
        "/api/users/auth/login",
        data={"username": "admin@example.com", "password": "AdminPass1!"},
    )
    assert response.status_code == 204, response.text
    session = (await anon_client.get(f"{_PROBE}/session")).json()
    assert session["gate_marker"] == "unlocked"
    assert "untrusted" not in session
