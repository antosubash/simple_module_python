"""The one-click demo sign-ins, and what the login page advertises.

Split from ``test_demo_account`` (configuration and seeding) and
``test_demo_guard`` (the read-only boundary): this is the entry itself —
the route, what it will and will not sign you in as, and the props the
sign-in card is drawn from.
"""

from __future__ import annotations

from _demo_support import DEMO_ADMIN_EMAIL, DEMO_USER_EMAIL
from users.constants import ADMIN_ROLE_NAME, USER_ROLE_NAME
from users.demo import ensure_demo_users
from users.models import User

_LOGIN_PAGE = "/users/login"
_INERTIA = {"X-Inertia": "true"}


def _demo_route(role: str) -> str:
    return f"/api/users/auth/demo/{role}"


async def _props(client) -> dict:
    return (await client.get(_LOGIN_PAGE, headers=_INERTIA)).json()["props"]


# ── the endpoint is absent unless configured ────────────────────────────────


async def test_both_routes_are_absent_when_demo_mode_is_off(anon_client):
    for role in (ADMIN_ROLE_NAME, USER_ROLE_NAME):
        assert (await anon_client.post(_demo_route(role))).status_code == 404


async def test_an_unknown_role_is_not_a_way_in(demo_client):
    assert (await demo_client.post(_demo_route("superuser"))).status_code == 404


async def test_a_blanked_account_stops_answering(demo_app, demo_client):
    """Blanking one email must close its route, not just hide its button."""
    demo_app.state.users.settings.demo_admin_email = ""

    assert (await demo_client.post(_demo_route(ADMIN_ROLE_NAME))).status_code == 404
    assert (await demo_client.post(_demo_route(USER_ROLE_NAME))).status_code == 204


async def test_a_disabled_row_is_not_a_way_in(demo_app, demo_client):
    """Disabling the account in the admin UI has to stop the button."""
    from datetime import UTC, datetime

    async with demo_app.state.sm.db.session_factory() as session:
        row = await session.get(User, demo_app.state.users.demo_user_ids[0])
        row.is_active = False
        row.disabled_at = datetime.now(UTC)
        await session.commit()

    assert (await demo_client.post(_demo_route(ADMIN_ROLE_NAME))).status_code == 404


# ── signing in ──────────────────────────────────────────────────────────────


async def test_one_click_signs_the_visitor_in_as_the_admin(demo_client):
    assert (await demo_client.post(_demo_route(ADMIN_ROLE_NAME))).status_code == 204

    me = await demo_client.get("/api/users/me")
    assert me.status_code == 200
    assert me.json()["email"] == DEMO_ADMIN_EMAIL


async def test_one_click_signs_the_visitor_in_as_the_standard_user(demo_client):
    assert (await demo_client.post(_demo_route(USER_ROLE_NAME))).status_code == 204

    assert (await demo_client.get("/api/users/me")).json()["email"] == DEMO_USER_EMAIL


async def test_the_two_demos_are_different_identities(demo_client):
    """The whole point of two buttons: the second must not land you back in
    the first one's session."""
    await demo_client.post(_demo_route(ADMIN_ROLE_NAME))
    first = (await demo_client.get("/api/users/me")).json()["id"]

    await demo_client.post(_demo_route(USER_ROLE_NAME))
    second = (await demo_client.get("/api/users/me")).json()["id"]

    assert first != second


async def test_switching_demos_needs_no_sign_out(demo_client):
    """Comparing the two surfaces is why there are two, so the sign-in routes
    stay reachable from inside a read-only demo session."""
    await demo_client.post(_demo_route(USER_ROLE_NAME))

    assert (await demo_client.post(_demo_route(ADMIN_ROLE_NAME))).status_code == 204
    assert (await demo_client.get("/api/users/me")).json()["email"] == DEMO_ADMIN_EMAIL


# ── what the sign-in card is drawn from ─────────────────────────────────────


async def test_the_login_page_offers_nothing_by_default(anon_client):
    assert (await _props(anon_client))["demo_signin"] == {"accounts": [], "read_only": True}


async def test_the_login_page_offers_both_accounts(demo_client):
    assert (await _props(demo_client))["demo_signin"] == {
        "accounts": [{"role": ADMIN_ROLE_NAME}, {"role": USER_ROLE_NAME}],
        "read_only": True,
    }


async def test_the_login_page_never_leaks_a_demo_password(demo_app, demo_client):
    demo_app.state.users.settings.demo_admin_password = "sup3r-s3cret-demo"
    await ensure_demo_users(demo_app)

    assert "sup3r-s3cret-demo" not in (await demo_client.get(_LOGIN_PAGE, headers=_INERTIA)).text


async def test_signing_in_turns_the_banner_on(demo_client):
    """The shared ``demo`` prop is what every shell reads to say "this is a
    demo". Before a button it is inactive; after one, it is not."""
    assert (await _props(demo_client))["demo"] == {"active": False, "readOnly": False}

    await demo_client.post(_demo_route(USER_ROLE_NAME))

    assert (await _props(demo_client))["demo"] == {"active": True, "readOnly": True}


async def test_the_offer_and_the_session_are_separate_props(demo_client):
    """Page props win the Inertia merge, so a page prop named ``demo`` would
    shadow the banner's shared prop on this page alone — a collision that
    breaks quietly and only here."""
    props = await _props(demo_client)

    assert set(props["demo"]) == {"active", "readOnly"}
    assert set(props["demo_signin"]) == {"accounts", "read_only"}
