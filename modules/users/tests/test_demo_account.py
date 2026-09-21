"""Demo accounts: how they are configured, seeded, and entered.

Two of the ways the feature can fail open live here — buttons that appear when
no account is configured, and an endpoint that signs someone in when the
feature is off. The third, a demo session that is allowed to write, is
``test_demo_guard``.
"""

from __future__ import annotations

from _demo_support import DEMO_ADMIN_EMAIL, DEMO_USER_EMAIL
from sqlalchemy import select
from users.constants import ADMIN_ROLE_NAME, USER_ROLE_NAME
from users.demo import (
    DemoAccount,
    ensure_demo_users,
    reconcile_demo_user,
    resolve_demo_account,
    resolve_demo_accounts,
)
from users.models import Role, User, UserRole
from users.settings import UsersSettings


def _settings(**overrides) -> UsersSettings:
    base = {
        "reset_password_token_secret": "test-reset-secret-32-bytes-xxxxx",
        "verification_token_secret": "test-verify-secret-32-bytes-xxxxx",
    }
    return UsersSettings(**base, **overrides)


# ── resolve_demo_accounts ───────────────────────────────────────────────────


def test_demo_is_off_by_default():
    assert resolve_demo_accounts(_settings()) == ()


def test_both_accounts_are_offered_admin_first():
    """Admin first: it is the surface someone evaluating the framework came
    to see, and button order is the only thing that says so."""
    accounts = resolve_demo_accounts(_settings(demo_mode=True))

    assert [a.role for a in accounts] == [ADMIN_ROLE_NAME, USER_ROLE_NAME]
    assert [a.email for a in accounts] == [DEMO_ADMIN_EMAIL, DEMO_USER_EMAIL]


def test_blanking_one_email_offers_only_the_other():
    accounts = resolve_demo_accounts(_settings(demo_mode=True, demo_admin_email="  "))

    assert [a.role for a in accounts] == [USER_ROLE_NAME]


def test_blanking_both_emails_reads_as_off_not_as_an_error():
    """A half-finished edit in the admin UI must not break the sign-in page."""
    assert (
        resolve_demo_accounts(_settings(demo_mode=True, demo_admin_email="", demo_user_email=""))
        == ()
    )


def test_resolve_by_role_finds_each_account():
    settings = _settings(demo_mode=True)

    assert resolve_demo_account(settings, ADMIN_ROLE_NAME).email == DEMO_ADMIN_EMAIL
    assert resolve_demo_account(settings, USER_ROLE_NAME).email == DEMO_USER_EMAIL
    assert resolve_demo_account(settings, "superuser") is None


def test_read_only_is_the_default_posture():
    assert _settings(demo_mode=True).demo_read_only is True


# ── seeding ─────────────────────────────────────────────────────────────────


async def _row(app, email: str) -> User | None:
    async with app.state.sm.db.session_factory() as session:
        return (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()


async def _role_names(app, user_id) -> list[str]:
    async with app.state.sm.db.session_factory() as session:
        return list(
            (
                await session.execute(
                    select(Role.name)
                    .join(UserRole, UserRole.role_id == Role.id)
                    .where(UserRole.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )


async def test_ensure_demo_users_seeds_both_accounts(users_app):
    users_app.state.users.settings.demo_mode = True

    ids = await ensure_demo_users(users_app)

    assert len(ids) == 2
    assert users_app.state.users.demo_user_ids == ids
    admin = await _row(users_app, DEMO_ADMIN_EMAIL)
    user = await _row(users_app, DEMO_USER_EMAIL)
    assert admin is not None and admin.is_superuser
    assert user is not None and not user.is_superuser
    assert all(row.is_active and row.is_verified for row in (admin, user))


async def test_each_account_gets_its_own_role(users_app):
    users_app.state.users.settings.demo_mode = True
    await ensure_demo_users(users_app)

    admin = await _row(users_app, DEMO_ADMIN_EMAIL)
    user = await _row(users_app, DEMO_USER_EMAIL)
    assert await _role_names(users_app, admin.id) == [ADMIN_ROLE_NAME]
    assert await _role_names(users_app, user.id) == [USER_ROLE_NAME]


async def test_a_blank_password_still_produces_usable_accounts(users_app):
    """The buttons do not need passwords; the rows still need hashes."""
    users_app.state.users.settings.demo_mode = True
    await ensure_demo_users(users_app)

    assert (await _row(users_app, DEMO_ADMIN_EMAIL)).hashed_password
    assert (await _row(users_app, DEMO_USER_EMAIL)).hashed_password


async def test_a_generated_password_is_not_re_rolled_on_every_boot(users_app):
    """Re-hashing a secret nobody can use would write an audit entry per
    worker per restart, for no gain."""
    users_app.state.users.settings.demo_mode = True
    await ensure_demo_users(users_app)
    first = (await _row(users_app, DEMO_ADMIN_EMAIL)).hashed_password

    await ensure_demo_users(users_app)

    assert (await _row(users_app, DEMO_ADMIN_EMAIL)).hashed_password == first


async def test_a_configured_password_is_reapplied(users_app):
    """Changing a demo password in the admin UI has to take effect."""
    users_app.state.users.settings.demo_mode = True
    await ensure_demo_users(users_app)
    first = (await _row(users_app, DEMO_USER_EMAIL)).hashed_password

    users_app.state.users.settings.demo_user_password = "a-published-demo-password"
    await ensure_demo_users(users_app)

    assert (await _row(users_app, DEMO_USER_EMAIL)).hashed_password != first


async def test_demo_off_clears_the_cached_ids(users_app):
    users_app.state.users.settings.demo_mode = True
    await ensure_demo_users(users_app)
    users_app.state.users.settings.demo_mode = False

    assert await ensure_demo_users(users_app) == ()
    assert users_app.state.users.demo_user_ids == ()


async def test_repointing_an_email_demotes_the_account_that_held_it(users_app):
    """An address that served as the demo admin and is then configured as the
    demo user must lose the admin grant, or the demotion is cosmetic."""
    shared = "demo@example.com"
    async with users_app.state.sm.db.session_factory() as session:
        user = await reconcile_demo_user(
            session,
            DemoAccount(role=ADMIN_ROLE_NAME, email=shared, password="x", full_name="Demo"),
        )
        assert user.is_superuser
        await reconcile_demo_user(
            session,
            DemoAccount(role=USER_ROLE_NAME, email=shared, password="x", full_name="Demo"),
        )

    assert await _role_names(users_app, user.id) == [USER_ROLE_NAME]
    async with users_app.state.sm.db.session_factory() as session:
        refreshed = await session.get(User, user.id)
    assert not refreshed.is_superuser
