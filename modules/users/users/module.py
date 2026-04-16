"""Users module — local user management (replaces Keycloak)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

if TYPE_CHECKING:
    from fastapi import FastAPI


class UsersModule(ModuleBase):
    meta = ModuleMeta(
        name="Users",
        route_prefix="/api/users",
        view_prefix="/users",
        depends_on=["Auth"],
    )

    def register_settings(self, app: FastAPI) -> None:
        from users.settings import UsersSettings

        app.state.users_settings = UsersSettings()

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            "Users",
            ["users.manage", "users.self.profile"],
        )
        registry.map_role("user", ["users.self.profile"])

    def register_menu_items(self, registry: MenuRegistry) -> None:
        # Admin-only user management
        registry.add(
            MenuItem(
                label="Users",
                url="/users/admin",
                icon="users",
                order=30,
                section=MenuSection.SIDEBAR,
                roles=["admin"],
            )
        )
        # Self-service: profile + logout live in the user dropdown.
        registry.add(
            MenuItem(
                label="Profile",
                url="/users/me",
                icon="user",
                order=990,
                section=MenuSection.USER_DROPDOWN,
            )
        )
        registry.add(
            MenuItem(
                label="Logout",
                url="/users/logout",
                icon="log-out",
                order=999,
                section=MenuSection.USER_DROPDOWN,
                method="post",
            )
        )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from users.endpoints.api import register_auth_routes
        from users.endpoints.views import router as views
        from users.settings import UsersSettings

        # UsersSettings reads from env every time — safe and idempotent.
        # app.state is not accessible here so we re-parse from environment.
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

        s = app.state.users_settings
        app.state.mailer = build_mailer(s)
        app.state.rate_limiter = LoginRateLimiter(
            max_failures=s.login_rate_limit_failures,
            window_seconds=s.login_rate_limit_window_seconds,
            cooldown_seconds=s.login_rate_limit_cooldown_seconds,
        )
        app.state.auth_throughput_limiter = ThroughputLimiter(
            max_attempts=s.auth_rate_limit_attempts,
            window_seconds=s.auth_rate_limit_window_seconds,
        )
        reconfigure_cookie_transport(auth_backend, s)

        # Bootstrap + roles-cache hit different tables and have no data
        # dependency on each other — run them concurrently to shave a DB
        # round-trip off startup.
        await asyncio.gather(
            bootstrap_admin_from_env(app),
            refresh_roles_cache(app),
        )
