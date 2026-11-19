"""What ``UsersModule.on_startup`` builds once the DB-hydrated settings exist.

Extracted from ``users.module`` so that file stays a declaration of what this
module *registers* — routes, menus, permissions, settings — while this one owns
what it *constructs* at boot: the mailer, the two rate limiters, the OAuth client
map, the cookie transport, the revocation cache's window, the seeded admin, and
the reconciled demo accounts.

The split is not cosmetic. Everything here has to run after
``hydrate_settings_from_db``, because each piece reads a value an operator may
have changed in the admin UI; nothing in ``module.py`` may. Keeping the two apart
makes that ordering visible instead of a comment.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from fastapi import FastAPI

    from users.module import UsersModule

__all__ = [
    "run_startup",
]

logger = logging.getLogger(__name__)


async def run_startup(module: UsersModule, app: FastAPI) -> None:
    """Populate ``app.state.users`` and apply settings-derived configuration."""
    from users.accounts.backend import reconfigure_cookie_transport
    from users.accounts.session_version_cache import configure_session_version_cache
    from users.admin.summary_cache import register_writes
    from users.core.bootstrap import bootstrap_admin_from_env, ensure_user_role
    from users.core.roles_cache import refresh_roles_cache
    from users.demo import ensure_demo_users
    from users.web.deps import auth_backend

    register_writes(app)
    state = app.state.users
    s = state.settings

    _build_mailer(app, state, s)
    _build_limiters(state, s)
    _build_oauth_clients(app)

    from simple_module_hosting.auth_policy import session_cookie_is_secure

    reconfigure_cookie_transport(
        auth_backend, s, cookie_secure=session_cookie_is_secure(app.state.sm.settings)
    )
    # The revocation cache's staleness window is an operator choice: the default
    # trades one indexed read per request for a bounded window in which another
    # worker's revocation is not yet seen here. ``users.accounts.session_revocation``
    # closes that window wherever an invalidation transport is installed, so
    # this is the bound on a dropped message rather than on every revocation.
    configure_session_version_cache(s.session_version_cache_ttl_seconds)

    # Schema-only hosts need the signup role. Admin roles come from migrations
    # or explicit provisioning; ordinary startup must preserve operator changes.
    try:
        async with app.state.sm.db.session_factory.begin() as db:
            await ensure_user_role(db)
    except IntegrityError:
        # Another worker may have inserted the role during startup.
        logger.debug("users.startup.role_seed_raced", extra={"role_seed": "ensure_user_role"})

    await bootstrap_admin_from_env(app)
    # After the env bootstrap, not beside it: that one only runs while the
    # users table is empty, and the demo accounts have to be reconciled on
    # every boot so a change to either email or password takes effect.
    await ensure_demo_users(app)
    # Cache only after every startup path that can provision roles has finished.
    await refresh_roles_cache(app)


def _build_mailer(app: FastAPI, state, s) -> None:
    from users.mailer import build_mailer, default_app_name

    def _app_name() -> str:
        # Read the (optional) branding module's live name off app.state by
        # name — never imported, so users stays decoupled from branding.
        branding = getattr(app.state, "branding", None)
        name = getattr(getattr(branding, "settings", None), "app_name", None)
        return name or default_app_name()

    from simple_module_hosting.public_urls import public_origin

    def origin() -> str:
        host = getattr(getattr(app.state, "host", None), "settings", None)
        current = getattr(getattr(app.state, "users", None), "settings", s)
        return public_origin(host, current.base_url)

    state.mailer = build_mailer(
        s, _app_name, template_dirs=s.mail_template_dirs, base_url_provider=origin
    )


def _build_limiters(state, s) -> None:
    from users.auth_local.rate_limit import ThroughputLimiter

    state.auth_throughput_limiter = ThroughputLimiter(
        max_attempts=s.auth_rate_limit_attempts,
        window_seconds=s.auth_rate_limit_window_seconds,
    )


def _build_oauth_clients(app: FastAPI) -> None:
    from users.oauth.registry import build_registered_providers

    clients, buttons = build_registered_providers(app)
    app.state.users.oauth_clients = clients
    app.state.users.oauth_providers = buttons
