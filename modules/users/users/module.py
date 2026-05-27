"""Users module — local-account authentication and user management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from users.constants import (
    ADMIN_ROLE_NAME,
    PERM_USERS_MANAGE,
    PERM_USERS_SELF_PROFILE,
    USER_ROLE_NAME,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

_MODULE_DEPENDENCY_AUTH = "Auth"

# Menu URLs
_URL_USERS_ADMIN = "/users/admin"
_URL_USERS_ME = "/users/me"
_URL_USERS_LOGOUT = "/users/logout"

# Menu icons
_ICON_USERS = "users"
_ICON_USER = "user"
_ICON_LOG_OUT = "log-out"


class UsersModule(ModuleBase):
    meta = ModuleMeta(
        name="Users",
        route_prefix="/api/users",
        view_prefix="/users",
        depends_on=[_MODULE_DEPENDENCY_AUTH],
    )

    def register_settings(self, app: FastAPI) -> None:
        import importlib

        from users.settings import UsersSettings
        from users.state import UsersState

        # SM009 is AST-based: a static `from settings.registration import ...`
        # from a module helper is fine (plugin→plugin), but we resolve via
        # importlib here to match the convention used framework-side and to
        # keep the dependency direction one-way explicit.
        register_module_settings = importlib.import_module(
            "settings.registration"
        ).register_module_settings

        register_module_settings(app, "users", UsersSettings, lambda s: UsersState(settings=s))

        from users.provider import UsersAuthProvider

        app.state.auth.auth_provider = UsersAuthProvider()

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            "Users",
            [PERM_USERS_MANAGE, PERM_USERS_SELF_PROFILE],
        )
        registry.map_role(USER_ROLE_NAME, [PERM_USERS_SELF_PROFILE])

    def register_menu_items(self, registry: MenuRegistry) -> None:
        # Admin-only user management
        registry.add(
            MenuItem(
                label="Users",
                url=_URL_USERS_ADMIN,
                icon=_ICON_USERS,
                order=100,
                section=MenuSection.SIDEBAR,
                roles=[ADMIN_ROLE_NAME],
                group="Administration",
            )
        )
        # Self-service: profile + logout live in the user dropdown.
        registry.add(
            MenuItem(
                label="Profile",
                url=_URL_USERS_ME,
                icon=_ICON_USER,
                order=990,
                section=MenuSection.USER_DROPDOWN,
            )
        )
        registry.add(
            MenuItem(
                label="Logout",
                url=_URL_USERS_LOGOUT,
                icon=_ICON_LOG_OUT,
                order=999,
                section=MenuSection.USER_DROPDOWN,
                method="post",
            )
        )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from users.admin.api import admin_router
        from users.admin.views import router as admin_views
        from users.auth_local import api as auth_local_api
        from users.auth_local.views import router as auth_views
        from users.contracts.schemas import UserCreate, UserRead
        from users.deps import fastapi_users
        from users.oauth.api import register_oauth_routes
        from users.settings import UsersSettings

        # Consumed only by ``register_oauth_routes`` → ``build_clients`` at
        # registration time, which reads class-attribute defaults captured by
        # ``env_str()`` at import. Request-time readers of mutable fields
        # (e.g. ``login_redirect_url``) must go through
        # ``request.app.state.users.settings``, not this instance.
        settings = UsersSettings()

        api_router.include_router(auth_local_api.router)
        api_router.include_router(admin_router)
        # Throughput-wrap the stock fastapi-users routers; ``require_signup_enabled``
        # gates /register at request time so ``allow_signup`` is hot-reloadable.
        api_router.include_router(
            fastapi_users.get_reset_password_router(),
            prefix="/auth",
            tags=["users-auth"],
            dependencies=[Depends(auth_local_api.enforce_auth_throughput_limit)],
        )
        api_router.include_router(
            fastapi_users.get_verify_router(UserRead),
            prefix="/auth",
            tags=["users-auth"],
            dependencies=[Depends(auth_local_api.enforce_auth_throughput_limit)],
        )
        api_router.include_router(
            fastapi_users.get_register_router(UserRead, UserCreate),
            prefix="/auth",
            tags=["users-auth"],
            dependencies=[
                Depends(auth_local_api.require_signup_enabled),
                Depends(auth_local_api.enforce_auth_throughput_limit),
            ],
        )
        register_oauth_routes(api_router, settings)

        view_router.include_router(auth_views)
        view_router.include_router(admin_views)

    async def on_startup(self, app: FastAPI) -> None:
        """Build the mailer, rate limiter, and apply production cookie params."""
        import asyncio

        from users.auth_local.rate_limit import LoginRateLimiter, ThroughputLimiter
        from users.backend import reconfigure_cookie_transport
        from users.bootstrap import bootstrap_admin_from_env
        from users.deps import auth_backend
        from users.mailer import build_mailer
        from users.oauth.providers import enabled_provider_names
        from users.roles_cache import refresh_roles_cache

        state = app.state.users
        s = state.settings
        state.mailer = build_mailer(s)
        state.rate_limiter = LoginRateLimiter(
            max_failures=s.login_rate_limit_failures,
            window_seconds=s.login_rate_limit_window_seconds,
            cooldown_seconds=s.login_rate_limit_cooldown_seconds,
        )
        state.auth_throughput_limiter = ThroughputLimiter(
            max_attempts=s.auth_rate_limit_attempts,
            window_seconds=s.auth_rate_limit_window_seconds,
        )
        state.oauth_providers = enabled_provider_names(s)

        # Auto-fall-back when the default ``/dashboard/`` target is
        # unreachable because the Dashboard module isn't installed (e.g.
        # ``--preset minimal`` or apps like smpy_gis that omit it).
        # Pick the first sibling module that exposes view routes instead
        # of hard-coding ``/`` which may itself 404 (#173). Operator-set
        # overrides are always preserved.
        if s.login_redirect_url == "/dashboard/" and not any(
            m.meta.name == "Dashboard" for m in app.state.sm.modules
        ):
            first_view = next(
                (
                    m.meta.view_prefix
                    for m in app.state.sm.modules
                    if m.meta.view_prefix and m.meta.name != self.meta.name
                ),
                None,
            )
            s.login_redirect_url = f"{first_view}/" if first_view else "/"

        reconfigure_cookie_transport(auth_backend, s)

        await asyncio.gather(
            bootstrap_admin_from_env(app),
            refresh_roles_cache(app),
        )
