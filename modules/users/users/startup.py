"""Two self-contained decisions ``UsersModule.on_startup`` makes.

Neither is about *sequencing* the boot — which is what the hook itself is for
— so they live here and it reads as a list of steps. Pulled out when the hook
grew past the 300-line file cap and the alternative was to compress the
comments that explain why each one exists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from users.settings import UsersSettings

_FALLBACK_REDIRECT = "/"


def register_mailer_health_check(app: FastAPI, module_name: str) -> None:
    """Add the mailer check to the health registry.

    Registered at startup rather than in ``register_health_checks`` because the
    check needs the app to re-read DB-hydrated settings on every run. The owner
    is passed explicitly since the boot-time ``set_owner`` window has long
    closed by then.
    """
    from simple_module_core.health import HealthCheck

    from users.health import CHECK_MAILER, build_mailer_check

    app.state.sm.health_registry.add(
        HealthCheck(
            name=CHECK_MAILER,
            check=build_mailer_check(app),
            module=module_name,
            # On demand only: this authenticates against the mail provider,
            # which must not happen on a readiness-probe timer.
            probe=False,
        )
    )


def apply_login_redirect_fallback(
    app: FastAPI, settings: UsersSettings, module_name: str, default_url: str
) -> None:
    """Retarget the default post-login URL when Dashboard isn't installed.

    ``/dashboard/`` is unreachable under ``smpy new --preset minimal`` and in
    apps like ``smpy_gis`` that omit the module. Picks the first sibling that
    exposes view routes rather than hard-coding ``/``, which may itself 404
    (#173). An operator-set override is never touched.
    """
    if settings.login_redirect_url != default_url:
        return
    if any(m.meta.name == "Dashboard" for m in app.state.sm.modules):
        return
    first_view = next(
        (
            m.meta.view_prefix
            for m in app.state.sm.modules
            if m.meta.view_prefix and m.meta.name != module_name
        ),
        None,
    )
    settings.login_redirect_url = f"{first_view}/" if first_view else _FALLBACK_REDIRECT
