"""Logout events identify the validated browser session, independently of bearer auth."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from _users_app_builders import _make_standard_user, user_row
from auth.core.constants import SESSION_ID_KEY
from simple_module_hosting.pipeline.session import SESSION_EXPIRES_AT_KEY
from simple_module_test import forge_session_cookie
from sqlalchemy import select
from users.contracts.events import UserLoggedOut
from users.core.constants import SESSION_USER_ID_KEY
from users.models import RevokedSession

CREDENTIALS = {"username": "admin@example.com", "password": "AdminPass1!"}


@pytest.mark.parametrize("path", ["/users/logout", "/api/users/auth/logout"])
@pytest.mark.parametrize("bearer_user", [None, "same", "different"])
async def test_logout_event_names_session_user(users_app, anon_client, path, bearer_user):
    session_user = await user_row(users_app, CREDENTIALS["username"])
    headers = {}
    if bearer_user is not None:
        email, password = session_user.email, CREDENTIALS["password"]
        if bearer_user == "different":
            other = await _make_standard_user(users_app)
            email, password = other.email, "UserPass1!"
        token = await anon_client.post(
            "/api/users/auth/token", json={"email": email, "password": password}
        )
        assert token.status_code == 200
        headers["Authorization"] = f"Bearer {token.json()['access_token']}"

    assert (await anon_client.post("/api/users/auth/login", data=CREDENTIALS)).status_code == 204
    cookie = anon_client.cookies.get("session")
    # Exercise the session without relying on the separate access-token cookie.
    anon_client.cookies.clear()
    anon_client.cookies.set("session", cookie)
    observed = []

    async def observe(event):
        observed.append(event)

    users_app.state.sm.event_bus.subscribe(UserLoggedOut, observe)
    response = await anon_client.post(path, headers=headers)
    assert response.status_code == (303 if path == "/users/logout" else 204)
    assert observed == [UserLoggedOut(user_id=session_user.id, email=session_user.email)]
    async with users_app.state.sm.db.session_factory() as db:
        assert (await db.execute(select(RevokedSession.user_id))).scalar_one() == session_user.id
    anon_client.cookies.clear()
    anon_client.cookies.set("session", cookie)
    assert (await anon_client.get("/api/users/me")).status_code == 401
    if headers:
        # Ending a browser session does not revoke the supplied bearer token.
        assert (await anon_client.get("/api/users/me", headers=headers)).json()["email"] == email


@pytest.mark.parametrize("path", ["/users/logout", "/api/users/auth/logout"])
@pytest.mark.parametrize(
    "session_kind",
    ["absent", "bad-signature", "unknown-user", "malformed-id", "expired", "revoked"],
)
async def test_logout_without_valid_session_publishes_nothing(
    users_app, anon_client, path, session_kind
):
    user = await user_row(users_app, CREDENTIALS["username"])
    token = await anon_client.post(
        "/api/users/auth/token", json={"email": user.email, "password": CREDENTIALS["password"]}
    )
    assert token.status_code == 200
    headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
    payload = {SESSION_USER_ID_KEY: str(user.id), SESSION_ID_KEY: "invalid-session"}
    if session_kind == "unknown-user":
        payload[SESSION_USER_ID_KEY] = str(uuid.uuid4())
    elif session_kind == "malformed-id":
        payload[SESSION_USER_ID_KEY] = "not-a-user-id"
    elif session_kind == "expired":
        payload[SESSION_EXPIRES_AT_KEY] = (datetime.now(UTC) - timedelta(days=1)).timestamp()
    elif session_kind == "revoked":
        async with users_app.state.sm.db.session_factory() as db:
            db.add(
                RevokedSession(
                    session_id=payload[SESSION_ID_KEY],
                    user_id=user.id,
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
            await db.commit()
    anon_client.cookies.clear()
    if session_kind != "absent":
        cookie = forge_session_cookie(str(users_app.state.sm.settings.secret_key), payload)
        if session_kind == "bad-signature":
            cookie += "tampered"
        anon_client.cookies.set("session", cookie)
    observed = []

    async def observe(event):
        observed.append(event)

    users_app.state.sm.event_bus.subscribe(UserLoggedOut, observe)
    response = await anon_client.post(path, headers=headers)
    assert response.status_code == (303 if path == "/users/logout" else 204)
    assert observed == []
    assert (await anon_client.get("/api/users/me", headers=headers)).status_code == 200
