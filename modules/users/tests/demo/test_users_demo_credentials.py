"""Demo read-only mode follows identities authenticated without demo cookies."""

import httpx
import pytest
from api_tokens.constants import TokenKind
from api_tokens.service import ApiTokenService
from simple_module_test import forge_session_cookie
from users.auth_local.token_api import _create_token_pair
from users.demo import ensure_demo_users
from users.models import User


@pytest.fixture
async def demo_credentials(demo_app):
    settings = demo_app.state.users.settings
    settings.demo_admin_password = "DemoPass1!"
    await ensure_demo_users(demo_app)
    user_id = demo_app.state.users.demo_user_ids[0]
    async with demo_app.state.sm.db.session_factory() as db:
        pair = await _create_token_pair(db, user_id, settings)
        _, pat = await ApiTokenService(db).create(
            kind=TokenKind.PERSONAL,
            name="pre-existing demo PAT",
            scopes=["users.manage", "api_tokens.use"],
            expires_in_days=1,
            max_lifetime_days=30,
            owner_user_id=user_id,
        )
        await db.commit()
    return {"bearer": pair.access_token, "pat": pat, "refresh": pair.refresh_token}


@pytest.mark.parametrize("credential", ["bearer", "pat"])
@pytest.mark.parametrize("read_only", [True, False])
async def test_demo_token_writes_follow_read_only_setting(
    demo_app, demo_client, demo_credentials, credential, read_only
):
    demo_app.state.users.settings.demo_read_only = read_only
    headers = {"Authorization": f"Bearer {demo_credentials[credential]}"}
    # A successful read proves this credential actually resolves the demo identity.
    assert (await demo_client.get("/api/users/admin", headers=headers)).status_code == 200
    # A role-less account: the PAT's scopes (users.manage, api_tokens.use) cover it, so
    # only the demo read-only gate decides. A target holding permissions beyond the
    # token's scopes is refused regardless (#624).
    async with demo_app.state.sm.db.session_factory() as db:
        plain = User(email="plain@example.com", hashed_password=None, is_external=True)
        db.add(plain)
        await db.commit()
        target = str(plain.id)
    response = await demo_client.patch(
        f"/api/users/admin/{target}",
        json={"email": "plain@example.com", "full_name": "Changed"},
        headers=headers,
    )
    assert response.status_code == (403 if read_only else 200), response.text
    if read_only:
        assert response.json() == {"detail": "DEMO_READ_ONLY"}
    else:
        assert response.json()["full_name"] == "Changed"


@pytest.mark.parametrize("credential", ["bearer", "pat"])
async def test_demo_token_inertia_write_uses_existing_refusal(
    demo_app, demo_client, demo_credentials, credential
):
    response = await demo_client.patch(
        f"/api/users/admin/{demo_app.state.users.demo_user_ids[1]}",
        json={"email": demo_app.state.users.settings.demo_user_email, "full_name": "Changed"},
        headers={
            "Authorization": f"Bearer {demo_credentials[credential]}",
            "X-Inertia": "true",
            "Referer": "http://testserver/admin/users/",
        },
    )
    assert response.status_code == 409
    assert response.headers["X-Inertia-Location"] == "http://testserver/admin/users/"


@pytest.mark.parametrize("operation", ["login", "refresh"])
async def test_demo_cannot_mint_token_pair_without_session(
    demo_app, demo_client, demo_credentials, operation
):
    if operation == "login":
        path = "/api/users/auth/token"
        body = {"email": demo_app.state.users.settings.demo_admin_email, "password": "DemoPass1!"}
    else:
        path = "/api/users/auth/token/refresh"
        body = {"refresh_token": demo_credentials["refresh"]}
    response = await demo_client.post(path, json=body)
    assert response.status_code == 403, response.text
    assert response.json() == {"detail": "DEMO_READ_ONLY"}
    # Refusal must not consume the refresh token or leave a login lockout slot.
    demo_app.state.users.settings.demo_read_only = False
    assert (await demo_client.post(path, json=body)).status_code == 200


async def test_demo_session_cannot_create_pat(demo_app):
    cookie = forge_session_cookie(
        str(demo_app.state.sm.settings.secret_key),
        {"user_id": str(demo_app.state.users.demo_user_ids[0]), "sm_csrf_token": "csrf"},
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=demo_app),
        base_url="http://testserver",
        cookies={"session": cookie},
    ) as client:
        response = await client.post(
            "/api/api_tokens/tokens/",
            json={"name": "demo", "scopes": ["users.manage"], "expires_in_days": 1},
            headers={"X-CSRF-Token": "csrf"},
        )
    assert response.status_code == 403
    assert response.json() == {"detail": "DEMO_READ_ONLY"}


async def test_real_bearer_account_can_still_write_on_demo_instance(demo_app, demo_client):
    response = await demo_client.post(
        "/api/users/auth/token", json={"email": "admin@example.com", "password": "AdminPass1!"}
    )
    assert response.status_code == 200
    response = await demo_client.patch(
        f"/api/users/admin/{demo_app.state.users.demo_user_ids[1]}",
        json={
            "email": demo_app.state.users.settings.demo_user_email,
            "full_name": "Real admin write",
        },
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Real admin write"


async def test_demo_token_login_still_checks_password(demo_app, demo_client, demo_credentials):
    response = await demo_client.post(
        "/api/users/auth/token",
        json={"email": demo_app.state.users.settings.demo_admin_email, "password": "wrong"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize("credential", ["bearer", "pat"])
async def test_demo_token_can_still_logout(demo_client, demo_credentials, credential):
    response = await demo_client.post(
        "/api/users/auth/logout",
        headers={"Authorization": f"Bearer {demo_credentials[credential]}"},
    )
    assert response.status_code == 204
