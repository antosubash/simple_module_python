"""``DemoReadOnlyMiddleware`` — what a shared demo session may and may not do.

Split from ``test_demo_account`` (which covers configuring and seeding the
account) because this is the security boundary: every test here is a way the
guard could fail open.
"""

from __future__ import annotations

import httpx
from _demo_support import DEMO_EMAIL
from users.demo import SESSION_DEMO_KEY
from users.demo_guard import DEMO_READ_ONLY_DETAIL

# ── read-only guard ─────────────────────────────────────────────────────────


async def test_a_demo_session_cannot_write(demo_client):
    await demo_client.post("/api/users/auth/demo")

    res = await demo_client.patch("/api/users/me", json={"full_name": "Owned"})
    assert res.status_code == 403
    assert res.json()["detail"] == DEMO_READ_ONLY_DETAIL


async def test_a_demo_session_can_still_read(demo_client):
    await demo_client.post("/api/users/auth/demo")
    assert (await demo_client.get("/api/users/me")).status_code == 200


async def test_a_demo_session_can_still_sign_out(demo_client):
    await demo_client.post("/api/users/auth/demo")
    assert (await demo_client.post("/api/users/auth/logout")).status_code == 204


async def test_an_inertia_write_gets_a_hard_redirect_not_a_raw_403(demo_client):
    """Inertia renders a non-Inertia body as a modal — on a showcase instance
    that reads as a crash. The protocol's own answer is 409 + Location."""
    await demo_client.post("/api/users/auth/demo")

    res = await demo_client.patch(
        "/api/users/me",
        json={"full_name": "Owned"},
        headers={"X-Inertia": "true", "Referer": "http://testserver/users/me"},
    )
    assert res.status_code == 409
    assert res.headers["X-Inertia-Location"] == "http://testserver/users/me"


async def test_writes_are_allowed_when_read_only_is_off(demo_app, demo_client):
    demo_app.state.users.settings.demo_read_only = False
    await demo_client.post("/api/users/auth/demo")

    res = await demo_client.patch("/api/users/me", json={"full_name": "Explorer"})
    assert res.status_code == 200


async def test_the_guard_leaves_other_accounts_alone(demo_app):
    """A real administrator on a demo instance is doing real work.

    Goes through an admin route rather than ``/api/users/me``: that one
    authenticates off the fastapi-users cookie, which a forged session cookie
    does not carry, so a 401 there would prove nothing about the guard.
    """
    from _users_app_builders import _make_admin_user
    from simple_module_test import forge_session_cookie

    admin = await _make_admin_user(demo_app)
    cookie = forge_session_cookie(
        str(demo_app.state.sm.settings.secret_key), {"user_id": str(admin.id)}
    )
    transport = httpx.ASGITransport(app=demo_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", cookies={"session": cookie}
    ) as client:
        res = await client.patch(
            f"/api/users/admin/{demo_app.state.users.demo_user_id}",
            json={"email": DEMO_EMAIL, "full_name": "Renamed By A Real Admin"},
        )
    assert res.status_code == 200


async def test_a_demo_session_cannot_reach_the_admin_write_routes(demo_app):
    """The showcase account may browse /admin/*, never mutate through it."""
    from simple_module_test import forge_session_cookie

    cookie = forge_session_cookie(
        str(demo_app.state.sm.settings.secret_key),
        {"user_id": str(demo_app.state.users.demo_user_id), SESSION_DEMO_KEY: True},
    )
    transport = httpx.ASGITransport(app=demo_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", cookies={"session": cookie}
    ) as client:
        res = await client.delete(f"/api/users/admin/{demo_app.state.users.demo_user_id}")
    assert res.status_code == 403
    assert res.json()["detail"] == DEMO_READ_ONLY_DETAIL


async def test_an_unstamped_session_on_the_demo_account_still_blocks(demo_app):
    """The stamp is sufficient, not necessary.

    Matching on the user id too is what catches a visitor who signed in with a
    published ``demo_password`` through the ordinary form — that session never
    passes through the demo endpoint, so it carries no stamp.
    """
    from simple_module_test import forge_session_cookie

    payload = {"user_id": str(demo_app.state.users.demo_user_id)}
    assert SESSION_DEMO_KEY not in payload
    cookie = forge_session_cookie(str(demo_app.state.sm.settings.secret_key), payload)
    transport = httpx.ASGITransport(app=demo_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", cookies={"session": cookie}
    ) as client:
        res = await client.patch("/api/users/me", json={"full_name": "Owned"})
    assert res.status_code == 403
