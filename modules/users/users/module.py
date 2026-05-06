"""Users module — local-account authentication and user management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
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

        from auth.contracts.schemas import UserContext

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

        def serialize_principal(user: UserContext) -> dict:
            return {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "roles": user.roles,
            }

        app.state.principal_serializer = serialize_principal

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
        from users.endpoints.api import register_auth_routes
        from users.endpoints.views import router as views
        from users.settings import UsersSettings

        # Construct settings here (re-reads env_str-bound fields like OAuth
        # client ids/secrets). Validators have already passed by this point —
        # ``register_settings`` ran first and would have raised on placeholders.
        register_auth_routes(api_router, UsersSettings())
        view_router.include_router(views)

    def register_middleware(self, app: FastAPI) -> None:
        from users.middleware import AuthMiddleware

        app.add_middleware(AuthMiddleware)

    async def on_startup(self, app: FastAPI) -> None:
        """Build the mailer, rate limiter, and apply production cookie params."""
        import asyncio

        from users.backend import reconfigure_cookie_transport
        from users.bootstrap import bootstrap_admin_from_env
        from users.deps import auth_backend
        from users.mailer import build_mailer
        from users.rate_limit import LoginRateLimiter, ThroughputLimiter
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

        # Auto-fall-back from the default ``/dashboard/`` to ``/`` when the
        # Dashboard module isn't installed, so ``--preset minimal`` doesn't
        # 404 on login. Operator-set overrides are preserved.
        if s.login_redirect_url == "/dashboard/" and not any(
            m.meta.name == "Dashboard" for m in app.state.sm.modules
        ):
            s.login_redirect_url = "/"

        reconfigure_cookie_transport(auth_backend, s)

        await asyncio.gather(
            bootstrap_admin_from_env(app),
            refresh_roles_cache(app),
        )
