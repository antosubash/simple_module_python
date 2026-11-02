"""A token never shows its owner's identity, and dies with ``api_tokens.use``.

Security verification, round 1 pass 4:

* N2 — a page rendered for a token (the 403 page of a refused page route, a
  public page) used to carry the owner's ``auth`` user, roles, permissions,
  menus and memberships in its shared props.
* N3 — a personal token kept working after its owner lost ``api_tokens.use``
  (and with it the means to list or revoke it).
"""

from __future__ import annotations

from typing import Any

from _api_tokens_support import CSRF_HEADERS, FLAGS_URL, INERTIA_HEADERS, SERVICE_URL, create_pat

USE = "api_tokens.use"


def _assert_anonymous_props(resp: Any, email: str) -> None:
    props = resp.json()["props"]
    assert props["auth"] == {"user": None, "isAuthenticated": False, "permissions": []}
    assert "tenant" not in props
    assert email not in resp.text


async def test_refused_page_does_not_render_the_owner(actor, bearer):
    async with actor(admin=True) as a:
        token = (await create_pat(a.client, [USE, "feature_flags.view"]))["token"]
        email = (await a.client.get("/users/me", headers=INERTIA_HEADERS)).json()["props"]["auth"][
            "user"
        ]["email"]

    resp = await bearer("GET", "/users/me", token, headers=INERTIA_HEADERS)
    assert resp.status_code == 403
    _assert_anonymous_props(resp, email)


async def test_public_page_renders_a_token_as_anonymous(actor, bearer):
    async with actor() as u:
        token = (await create_pat(u.client, [USE]))["token"]
        email = (await u.client.get("/users/me", headers=INERTIA_HEADERS)).json()["props"]["auth"][
            "user"
        ]["email"]

    resp = await bearer("GET", "/users/login", token, headers=INERTIA_HEADERS)
    assert resp.status_code == 200
    _assert_anonymous_props(resp, email)


def _revoke_use(app: Any, roles: list[str]) -> None:
    registry = app.state.sm.permissions
    for role in roles:
        registry._role_map.get(role, set()).discard(USE)
    registry._invalidate()


async def test_pat_stops_working_when_its_owner_loses_the_use_permission(app, actor, bearer):
    registry = app.state.sm.permissions
    registry.map_role("tenant:owner", ["feature_flags.view"])
    async with actor() as u:
        token = (await create_pat(u.client, [USE, "feature_flags.view"]))["token"]
    assert (await bearer("GET", FLAGS_URL, token)).status_code == 200

    # Still held through the tenant role: the check is tenant-aware.
    _revoke_use(app, ["user"])
    assert (await bearer("GET", FLAGS_URL, token)).status_code == 200

    _revoke_use(app, [r for r in registry.role_map if r.startswith("tenant:")])
    assert (await bearer("GET", FLAGS_URL, token)).status_code == 401


async def test_service_key_does_not_depend_on_the_use_permission(app, actor, bearer):
    registry = app.state.sm.permissions
    registry.map_role("user", ["feature_flags.view"])
    async with actor(admin=True) as a:
        resp = await a.client.post(
            SERVICE_URL,
            json={
                "name": "k",
                "roles": ["user"],
                "scopes": ["feature_flags.view"],
                "expires_in_days": 30,
            },
            headers=CSRF_HEADERS,
        )
        assert resp.status_code == 201, resp.text
        token = resp.json()["token"]
    _revoke_use(app, list(registry.role_map))
    assert (await bearer("GET", FLAGS_URL, token)).status_code == 200
