"""The admin "Copy reset link" origin.

It used ``users.base_url``, whose default is the dev origin, so every install
that had not set it copied links to ``http://localhost:8000``.
"""

from __future__ import annotations

import pytest
from _users_app_builders import _make_standard_user
from users.settings import UsersSettings

_STOCK = UsersSettings.model_fields["base_url"].default


@pytest.fixture(autouse=True)
def _stock_users_base_url(users_app):
    """The users fixture pins ``base_url`` to the test origin; restore the stock default."""
    users_app.state.users.settings.base_url = _STOCK


async def _link(admin_client, users_app) -> str:
    user = await _make_standard_user(users_app)
    resp = await admin_client.post(f"/api/users/admin/{user.id}/reset-password-link")
    assert resp.status_code == 200, resp.text
    return resp.json()["link"]


@pytest.mark.anyio
async def test_unconfigured_falls_back_to_the_serving_origin(admin_client, users_app):
    assert _STOCK == "http://localhost:8000"
    link = await _link(admin_client, users_app)
    assert link.startswith("http://testserver/users/reset-password?token="), link


@pytest.mark.anyio
async def test_public_base_url_wins_over_the_request(admin_client, users_app):
    users_app.state.host.settings.public_base_url = "https://app.example.org"
    link = await _link(admin_client, users_app)
    assert link.startswith("https://app.example.org/users/reset-password?token="), link


@pytest.mark.anyio
async def test_a_configured_users_base_url_matches_the_mailers(admin_client, users_app):
    users_app.state.host.settings.public_base_url = "https://app.example.org"
    users_app.state.users.settings.base_url = "https://accounts.example.org/"
    link = await _link(admin_client, users_app)
    assert link.startswith("https://accounts.example.org/users/reset-password?token="), link
