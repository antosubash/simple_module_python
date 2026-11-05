"""Browser auth mutations use the anonymous session's token."""

import pytest

LOGIN = "/api/users/auth/login"
CREDENTIALS = {"username": "admin@example.com", "password": "AdminPass1!"}


@pytest.mark.parametrize(
    "path",
    [
        LOGIN,
        "/api/users/auth/register",
        "/api/users/auth/forgot-password",
        "/api/users/auth/reset-password",
        "/api/users/auth/request-verify-token",
        "/api/users/auth/verify",
        "/api/users/auth/accept-invite",
        "/api/users/auth/demo/user",
        "/api/users/auth/logout",
    ],
)
async def test_browser_mutations_require_session_token(anon_client, path):
    for headers in [
        {"Origin": "https://other.example"},
        {"Origin": "null"},
        {"Referer": "https://other.example/form"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Origin": "http://testserver"},
    ]:
        response = await anon_client.post(path, headers=headers, data=CREDENTIALS)
        assert response.status_code == 403, (headers, response.text)
        assert "sm_auth=" not in response.headers.get("set-cookie", "")


async def test_anonymous_page_token_allows_login_and_rotates(anon_client):
    props = (
        await anon_client.get(
            "/users/login", headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"}
        )
    ).json()["props"]
    token = props["csrfToken"]
    headers = {"Origin": "http://testserver", "X-CSRF-Token": token}
    assert (await anon_client.post(LOGIN, data=CREDENTIALS, headers=headers)).status_code == 204
    assert (await anon_client.post(LOGIN, data=CREDENTIALS, headers=headers)).status_code == 403


@pytest.mark.parametrize("header", ["Origin", "Referer"])
async def test_foreign_source_refused_even_with_token(anon_client, header):
    token = (
        await anon_client.get(
            "/users/login", headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"}
        )
    ).json()["props"]["csrfToken"]
    response = await anon_client.post(
        LOGIN,
        data=CREDENTIALS,
        headers={header: "https://other.example", "X-CSRF-Token": token},
    )
    assert response.status_code == 403


async def test_non_browser_password_client_keeps_working(anon_client):
    assert (await anon_client.post(LOGIN, data=CREDENTIALS)).status_code == 204


async def test_view_logout_accepts_same_origin_inertia_post(anon_client):
    assert (await anon_client.post(LOGIN, data=CREDENTIALS)).status_code == 204
    refused = await anon_client.post("/users/logout", headers={"Origin": "https://other.example"})
    assert refused.status_code == 403
    assert (
        await anon_client.post("/users/logout", headers={"Origin": "http://testserver"})
    ).status_code == 303


@pytest.mark.parametrize(
    "path",
    [
        "/users/login",
        "/users/register",
        "/users/forgot-password",
        "/users/reset-password",
        "/users/verify",
        "/users/invite/accept",
    ],
)
async def test_anonymous_auth_pages_supply_token(anon_client_signup, path):
    response = await anon_client_signup.get(
        path, headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"}
    )
    assert response.status_code == 200
    assert response.json()["props"]["csrfToken"]
