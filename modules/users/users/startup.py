"""What ``UsersModule.on_startup`` builds once the DB-hydrated settings exist.

Extracted from ``users.module`` so that file stays a declaration of what this
module *registers* — routes, menus, permissions, settings — while this one owns
what it *constructs* at boot: the mailer, the two rate limiters, the OAuth client
map, the cookie transport, the revocation cache's window, and the seeded admin.

The split is not cosmetic. Everything here has to run after
``hydrate_settings_from_db``, because each piece reads a value an operator may
have changed in the admin UI; nothing in ``module.py`` may. Keeping the two apart
makes that ordering visible instead of a comment.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from users.module import UsersModule

__all__ = ["run_startup"]

_DEFAULT_LOGIN_REDIRECT = "/dashboard/"
_DASHBOARD_MODULE = "Dashboard"


async def run_startup(module: UsersModule, app: FastAPI) -> None:
    """Populate ``app.state.users`` and apply settings-derived configuration."""
    from users.backend import reconfigure_cookie_transport
    from users.bootstrap import bootstrap_admin_from_env
    from users.deps import auth_backend
    from users.roles_cache import refresh_roles_cache
    from users.session_version_cache import configure_session_version_cache

    state = app.state.users
    s = state.settings

    _build_mailer(app, state, s)
    _register_mailer_check(module, app)
    _build_limiters(state, s)
    _build_oauth_clients(state, s)
    _pick_login_redirect(module, app, s)

    reconfigure_cookie_transport(auth_backend, s)
    # The revocation cache's staleness window is an operator choice: the default
    # trades one indexed read per request for a bounded window in which another
    # worker's revocation is not yet seen here. ``users.session_revocation``
    # closes that window wherever an invalidation transport is installed, so
    # this is the bound on a dropped message rather than on every revocation.
    configure_session_version_cache(s.session_version_cache_ttl_seconds)

    await asyncio.gather(
        bootstrap_admin_from_env(app),
        refresh_roles_cache(app),
    )


def _build_mailer(app: FastAPI, state, s) -> None:
    from users.mailer import build_mailer, default_app_name

    def _app_name() -> str:
        # Read the (optional) branding module's live name off app.state by
        # name — never imported, so users stays decoupled from branding.
        branding = getattr(app.state, "branding", None)
        name = getattr(getattr(branding, "settings", None), "app_name", None)
        return name or default_app_name()

    state.mailer = build_mailer(s, _app_name)


def _register_mailer_check(module: UsersModule, app: FastAPI) -> None:
    """Registered here rather than in ``register_health_checks``.

    The check needs the app to re-read DB-hydrated settings on every run, and
    the owner is passed explicitly because the boot-time ``set_owner`` window
    has long closed by startup.
    """
    from simple_module_core.health import HealthCheck

    from users.health import CHECK_MAILER, build_mailer_check

    app.state.sm.health_registry.add(
        HealthCheck(
            name=CHECK_MAILER,
            check=build_mailer_check(app),
            module=module.meta.name,
            # On demand only: this authenticates against the mail provider,
            # which must not happen on a readiness-probe timer.
            probe=False,
        )
    )


def _build_limiters(state, s) -> None:
    from users.auth_local.rate_limit import LoginRateLimiter, ThroughputLimiter

    state.rate_limiter = LoginRateLimiter(
        max_failures=s.login_rate_limit_failures,
        window_seconds=s.login_rate_limit_window_seconds,
        cooldown_seconds=s.login_rate_limit_cooldown_seconds,
    )
    state.auth_throughput_limiter = ThroughputLimiter(
        max_attempts=s.auth_rate_limit_attempts,
        window_seconds=s.auth_rate_limit_window_seconds,
    )


def _build_oauth_clients(state, s) -> None:
    from users.oauth.providers import build_client_map, provider_buttons

    state.oauth_clients = build_client_map(s)
    state.oauth_providers = provider_buttons(state.oauth_clients)


def _pick_login_redirect(module: UsersModule, app: FastAPI, s) -> None:
    """Fall back off ``/dashboard/`` when the Dashboard module isn't installed.

    ``--preset minimal`` and apps like smpy_gis omit it. Picks the first sibling
    module that exposes view routes rather than hard-coding ``/``, which may
    itself 404 (#173). An operator-set override is always preserved.
    """
    if s.login_redirect_url != _DEFAULT_LOGIN_REDIRECT:
        return
    modules = app.state.sm.modules
    if any(m.meta.name == _DASHBOARD_MODULE for m in modules):
        return
    first_view = next(
        (
            m.meta.view_prefix
            for m in modules
            if m.meta.view_prefix and m.meta.name != module.meta.name
        ),
        None,
    )
    s.login_redirect_url = f"{first_view}/" if first_view else "/"
