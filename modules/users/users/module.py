"""Users module — local user management (replaces Keycloak)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
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
        """Build the mailer once app settings are committed."""
        from users.mailer import build_mailer

        app.state.mailer = build_mailer(app.state.users_settings)

        # Patch cookie transport params from real settings (dev-safe singleton
        # in deps.py is constructed with defaults at import time).
        from users.deps import auth_backend

        s = app.state.users_settings
        transport = auth_backend.transport
        transport.cookie_name = s.cookie_name
        transport.cookie_max_age = s.cookie_max_age_seconds
        transport.cookie_secure = s.cookie_secure
        transport.cookie_samesite = s.cookie_samesite
