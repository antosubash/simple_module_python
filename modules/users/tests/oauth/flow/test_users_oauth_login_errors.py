"""Browser OAuth refusals return to login; API clients keep JSON (#654)."""

from urllib.parse import parse_qs, urlparse

import pytest
from _users_oauth_support import install_fake_provider, oauth_callback, seed_password_user


@pytest.mark.anyio
async def test_browser_unverified_account_returns_to_login(users_app, anon_client):
    await seed_password_user(users_app, "refused@example.com", is_verified=False)
    install_fake_provider(users_app, "refused", "refused@example.com")
    anon_client.headers["accept"] = "text/html"

    response = await oauth_callback(anon_client)

    assert response.status_code == 303
    assert response.headers["location"] == "/users/login?oauth_error=account_not_verified"
    assert users_app.state.users.settings.cookie_name not in response.cookies


@pytest.mark.anyio
@pytest.mark.parametrize("browser", [True, False])
async def test_provider_refusal_is_sanitized(users_app, anon_client, browser):
    install_fake_provider(users_app, "refused", "refused@example.com")
    login = await anon_client.get("/api/users/auth/oidc/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    response = await anon_client.get(
        "/api/users/auth/oidc/callback",
        params={"state": state, "error": "<script>provider text</script>"},
        headers={"accept": "text/html" if browser else "application/json"},
        follow_redirects=False,
    )
    if browser:
        assert response.status_code == 303
        assert response.headers["location"] == "/users/login?oauth_error=signin_failed"
    else:
        assert response.status_code == 400
        assert response.json()["detail"] == "OAUTH_PROVIDER_ERROR"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "code", ["account_not_verified", "signup_disabled", "signin_failed", "<script>"]
)
async def test_login_only_exposes_known_oauth_errors(anon_client, code):
    response = await anon_client.get(
        "/users/login", params={"oauth_error": code}, headers={"X-Inertia": "true"}
    )
    assert response.status_code == 200
    assert response.json()["props"]["oauth_error"] == (None if code == "<script>" else code)
