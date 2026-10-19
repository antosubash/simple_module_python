"""A fake OAuth provider (no network) to drive the ``/login`` + ``/callback`` flow."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx


class _FakeOAuthClient:
    def __init__(self, account_id: str, account_email: str) -> None:
        self._account_id = account_id
        self._account_email = account_email

    async def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        return f"https://idp.example/authorize?state={state}"

    async def get_access_token(self, code: str, redirect_uri: str) -> dict:
        return {"access_token": "fake-token", "expires_at": None, "refresh_token": None}

    async def get_id_email(self, access_token: str) -> tuple[str, str]:
        return self._account_id, self._account_email


def install_fake_provider(app, account_id: str, account_email: str) -> None:
    from users.oauth import OAuthProvider

    app.state.users.oauth_clients["microsoft"] = OAuthProvider(
        "microsoft", "Microsoft", _FakeOAuthClient(account_id, account_email)
    )


def set_allow_signup(app, allowed: bool) -> None:
    """Flip ``allow_signup`` on the live settings, as an admin edit would."""
    settings = app.state.users.settings
    app.state.users.settings = settings.model_copy(update={"allow_signup": allowed})


async def oauth_callback(client: httpx.AsyncClient) -> httpx.Response:
    """Drive /login then /callback; return the callback response."""
    login = await client.get("/api/users/auth/microsoft/login", follow_redirects=False)
    assert login.status_code == 302
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    return await client.get(
        f"/api/users/auth/microsoft/callback?code=abc&state={state}",
        follow_redirects=False,
    )


async def run_oauth_login(client: httpx.AsyncClient) -> int:
    """Drive /login then /callback; return the callback status code."""
    return (await oauth_callback(client)).status_code
