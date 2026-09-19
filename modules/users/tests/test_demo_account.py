"""Demo account: how it is configured, seeded, and entered.

Two of the ways the feature can fail open live here — a demo button that
appears when no account is configured, and an endpoint that signs someone in
when the feature is off. The third, a demo session that is allowed to write,
is ``test_demo_guard``.
"""

from __future__ import annotations

from _demo_support import DEMO_EMAIL
from sqlalchemy import select
from users.constants import ADMIN_ROLE_NAME, USER_ROLE_NAME
from users.demo import (
    DemoAccount,
    ensure_demo_user,
    reconcile_demo_user,
    resolve_demo_account,
)
from users.models import Role, User, UserRole
from users.settings import UsersSettings


def _settings(**overrides) -> UsersSettings:
    base = {
        "reset_password_token_secret": "test-reset-secret-32-bytes-xxxxx",
        "verification_token_secret": "test-verify-secret-32-bytes-xxxxx",
    }
    return UsersSettings(**base, **overrides)


# ── resolve_demo_account ────────────────────────────────────────────────────


def test_demo_is_off_by_default():
    assert resolve_demo_account(_settings()) is None


def test_blank_email_reads_as_off_not_as_an_error():
    """A half-finished edit in the admin UI must not break the sign-in page."""
    assert resolve_demo_account(_settings(demo_mode=True, demo_email="  ")) is None


def test_an_unknown_role_falls_back_to_the_standard_one():
    """Never silently upgrade: an unrecognised value must not mean admin.

    ``demo_role`` carries a pydantic pattern, so this can only come from a
    value written straight into the settings table — which is exactly the case
    the fallback is there for, and why it is tested through ``model_construct``
    rather than the validated constructor.
    """
    raw = UsersSettings.model_construct(
        demo_mode=True,
        demo_email=DEMO_EMAIL,
        demo_password="",
        demo_full_name="Demo User",
        demo_role="superuser",
        demo_read_only=True,
    )
    account = resolve_demo_account(raw)
    assert account is not None
    assert account.role == USER_ROLE_NAME


def test_read_only_is_the_default_posture():
    account = resolve_demo_account(_settings(demo_mode=True))
    assert account is not None and account.read_only is True


# ── seeding ─────────────────────────────────────────────────────────────────


async def _demo_row(app) -> User | None:
    async with app.state.sm.db.session_factory() as session:
        return (
            await session.execute(select(User).where(User.email == DEMO_EMAIL))
        ).scalar_one_or_none()


async def test_ensure_demo_user_seeds_the_account(users_app):
    users_app.state.users.settings.demo_mode = True
    user_id = await ensure_demo_user(users_app)

    assert user_id is not None
    assert users_app.state.users.demo_user_id == user_id
    row = await _demo_row(users_app)
    assert row is not None
    assert row.is_active and row.is_verified and not row.is_superuser


async def test_a_blank_password_still_produces_a_usable_account(users_app):
    """The button does not need a password; the row still needs a hash."""
    users_app.state.users.settings.demo_mode = True
    await ensure_demo_user(users_app)

    row = await _demo_row(users_app)
    assert row is not None and row.hashed_password


async def test_a_generated_password_is_not_re_rolled_on_every_boot(users_app):
    """Re-hashing a secret nobody can use would write an audit entry per
    worker per restart, for no gain."""
    users_app.state.users.settings.demo_mode = True
    await ensure_demo_user(users_app)
    first = (await _demo_row(users_app)).hashed_password

    await ensure_demo_user(users_app)

    assert (await _demo_row(users_app)).hashed_password == first


async def test_a_configured_password_is_reapplied(users_app):
    """Changing demo_password in the admin UI has to take effect."""
    users_app.state.users.settings.demo_mode = True
    await ensure_demo_user(users_app)
    first = (await _demo_row(users_app)).hashed_password

    users_app.state.users.settings.demo_password = "a-published-demo-password"
    await ensure_demo_user(users_app)

    assert (await _demo_row(users_app)).hashed_password != first


async def test_demo_off_clears_the_cached_id(users_app):
    users_app.state.users.settings.demo_mode = True
    await ensure_demo_user(users_app)
    users_app.state.users.settings.demo_mode = False

    assert await ensure_demo_user(users_app) is None
    assert users_app.state.users.demo_user_id is None


async def test_demoting_the_role_drops_the_admin_grant(users_app):
    """Flipping demo_role back is how an operator revokes a too-open demo."""
    async with users_app.state.sm.db.session_factory() as session:
        account = DemoAccount(
            email=DEMO_EMAIL, password="x", full_name="Demo", role=ADMIN_ROLE_NAME, read_only=True
        )
        user = await reconcile_demo_user(session, account)
        assert user.is_superuser

        await reconcile_demo_user(
            session,
            DemoAccount(
                email=DEMO_EMAIL,
                password="x",
                full_name="Demo",
                role=USER_ROLE_NAME,
                read_only=True,
            ),
        )

    async with users_app.state.sm.db.session_factory() as session:
        roles = (
            (
                await session.execute(
                    select(Role.name)
                    .join(UserRole, UserRole.role_id == Role.id)
                    .where(UserRole.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
        refreshed = await session.get(User, user.id)
    assert roles == [USER_ROLE_NAME]
    assert refreshed is not None and not refreshed.is_superuser


# ── endpoint + login page ───────────────────────────────────────────────────


async def test_the_endpoint_is_absent_when_demo_mode_is_off(anon_client):
    res = await anon_client.post("/api/users/auth/demo")
    assert res.status_code == 404


async def test_the_login_page_advertises_no_demo_by_default(anon_client):
    res = await anon_client.get("/users/login", headers={"X-Inertia": "true"})
    assert res.status_code == 200
    assert res.json()["props"]["demo_signin"] == {"enabled": False, "read_only": False}


async def test_the_login_page_advertises_the_demo(demo_client):
    res = await demo_client.get("/users/login", headers={"X-Inertia": "true"})
    assert res.json()["props"]["demo_signin"] == {"enabled": True, "read_only": True}


async def test_the_login_page_never_leaks_the_demo_password(demo_app, demo_client):
    demo_app.state.users.settings.demo_password = "sup3r-s3cret-demo"
    await ensure_demo_user(demo_app)

    res = await demo_client.get("/users/login", headers={"X-Inertia": "true"})
    assert "sup3r-s3cret-demo" not in res.text


async def test_a_disabled_demo_account_is_not_a_way_in(demo_app, demo_client):
    """Disabling the row in the admin UI has to actually stop the button."""
    from datetime import UTC, datetime

    async with demo_app.state.sm.db.session_factory() as session:
        row = await session.get(User, demo_app.state.users.demo_user_id)
        row.is_active = False
        row.disabled_at = datetime.now(UTC)
        await session.commit()

    assert (await demo_client.post("/api/users/auth/demo")).status_code == 404


async def test_one_click_signs_the_visitor_in(demo_client):
    res = await demo_client.post("/api/users/auth/demo")
    assert res.status_code == 204

    me = await demo_client.get("/api/users/me")
    assert me.status_code == 200
    assert me.json()["email"] == DEMO_EMAIL


async def test_signing_in_turns_the_banner_on(demo_client):
    """The shared ``demo`` prop is what every shell reads to say "this is a
    demo". Before the button it is inactive; after it, it is not."""
    before = (await demo_client.get("/users/login", headers={"X-Inertia": "true"})).json()
    assert before["props"]["demo"] == {"active": False, "readOnly": False}

    await demo_client.post("/api/users/auth/demo")

    after = (await demo_client.get("/users/login", headers={"X-Inertia": "true"})).json()
    assert after["props"]["demo"] == {"active": True, "readOnly": True}


async def test_the_offer_and_the_session_are_separate_props(demo_client):
    """Page props win the Inertia merge, so a page prop named ``demo`` would
    shadow the banner's shared prop on this page alone — a collision that
    breaks quietly and only here."""
    props = (await demo_client.get("/users/login", headers={"X-Inertia": "true"})).json()["props"]

    assert set(props["demo"]) == {"active", "readOnly"}
    assert set(props["demo_signin"]) == {"enabled", "read_only"}
