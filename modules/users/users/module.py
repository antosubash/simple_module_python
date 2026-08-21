"""Users module — local-account authentication and user management."""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from simple_module_core.audit_links import AuditLink, AuditLinkRegistry
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
    from simple_module_core.events import EventBus

_MODULE_DEPENDENCY_AUTH = "Auth"
# register_settings() goes through settings.registration.register_module_settings,
# which reads app.state.settings — so Settings must register first.
_MODULE_DEPENDENCY_SETTINGS = "Settings"

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
        depends_on=[_MODULE_DEPENDENCY_AUTH, _MODULE_DEPENDENCY_SETTINGS],
    )
    _is_auth_provider = True

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

        # The public shell renders a "Sign up" link only when signup is open —
        # /users/register 404s otherwise. Registered here (not in the view
        # layer) so it is set before the first request is served.
        from simple_module_hosting.shared_props import register_inertia_shared_provider

        from users.shared_props import users_shared_props

        register_inertia_shared_provider(app, users_shared_props)

    def register_event_handlers(self, bus: EventBus, app: FastAPI | None = None) -> None:
        """Rebuild the OAuth client cache when the users settings reload.

        Routes mount at construction (before DB hydration), so the cache is the
        single source of truth at request time. Rebuilding it here lets an admin
        add/remove a provider via the settings UI without a restart.
        """
        if app is None:
            return

        import importlib

        settings_reloaded = importlib.import_module("settings.contracts.events").SettingsReloaded
        from users.oauth.providers import build_client_map, provider_buttons

        async def _rebuild_oauth_clients(event: settings_reloaded) -> None:
            if event.package != "users":
                return
            state = app.state.users
            state.oauth_clients = build_client_map(state.settings)
            state.oauth_providers = provider_buttons(state.oauth_clients)

        bus.subscribe(settings_reloaded, _rebuild_oauth_clients)

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            "Users",
            [PERM_USERS_MANAGE, PERM_USERS_SELF_PROFILE],
        )
        registry.map_role(USER_ROLE_NAME, [PERM_USERS_SELF_PROFILE])

    def register_audit_links(self, registry: AuditLinkRegistry) -> None:
        from users.models import User

        registry.register(
            AuditLink(
                # The model class name — what snapshot_changes records. Keying
                # this off __tablename__ ("users_user") silently never matches.
                entity_type=User.__name__,
                url_template=f"{_URL_USERS_ADMIN}/{{id}}",
                label="User",
                label_key="users.audit.user",
            )
        )

    def register_menu_items(self, registry: MenuRegistry) -> None:
        # Admin-only user management
        registry.add(
            MenuItem(
                label="Users",
                label_key="users.nav.users",
                url=_URL_USERS_ADMIN,
                icon=_ICON_USERS,
                order=100,
                section=MenuSection.SIDEBAR,
                roles=[ADMIN_ROLE_NAME],
                group="Administration",
                group_key="ui.nav_groups.administration",
            )
        )
        # Self-service: profile + logout live in the user dropdown.
        registry.add(
            MenuItem(
                label="Profile",
                label_key="users.nav.profile",
                url=_URL_USERS_ME,
                icon=_ICON_USER,
                order=990,
                section=MenuSection.USER_DROPDOWN,
            )
        )
        registry.add(
            MenuItem(
                label="Logout",
                label_key="users.nav.logout",
                url=_URL_USERS_LOGOUT,
                icon=_ICON_LOG_OUT,
                order=999,
                section=MenuSection.USER_DROPDOWN,
                method="post",
            )
        )

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {"users": base}

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from users.admin.api import admin_router
        from users.admin.views import router as admin_views
        from users.auth_local import api as auth_local_api
        from users.auth_local.token_api import router as token_router
        from users.auth_local.views import router as auth_views
        from users.contracts.schemas import UserCreate, UserRead
        from users.deps import fastapi_users
        from users.oauth.api import register_oauth_routes

        api_router.include_router(auth_local_api.router)
        api_router.include_router(token_router)
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
        register_oauth_routes(api_router)

        view_router.include_router(auth_views)
        view_router.include_router(admin_views)

    async def on_startup(self, app: FastAPI) -> None:
        """Build the mailer, rate limiter, and apply production cookie params."""
        import asyncio

        from users.auth_local.rate_limit import LoginRateLimiter, ThroughputLimiter
        from users.backend import reconfigure_cookie_transport
        from users.bootstrap import bootstrap_admin_from_env
        from users.deps import auth_backend
        from users.mailer import build_mailer, default_app_name
        from users.oauth.providers import build_client_map, provider_buttons
        from users.roles_cache import refresh_roles_cache

        state = app.state.users
        s = state.settings

        def _app_name() -> str:
            # Read the (optional) branding module's live name off app.state by
            # name — never imported, so users stays decoupled from branding.
            branding = getattr(app.state, "branding", None)
            name = getattr(getattr(branding, "settings", None), "app_name", None)
            return name or default_app_name()

        state.mailer = build_mailer(s, _app_name)

        # Registered here rather than in register_health_checks because the
        # check needs the app to re-read DB-hydrated settings on every run.
        # The owner is passed explicitly since the boot-time set_owner window
        # has long closed by startup.
        from simple_module_core.health import HealthCheck

        from users.health import CHECK_MAILER, build_mailer_check

        app.state.sm.health_registry.add(
            HealthCheck(
                name=CHECK_MAILER,
                check=build_mailer_check(app),
                module=self.meta.name,
                # On demand only: this authenticates against the mail provider,
                # which must not happen on a readiness-probe timer.
                probe=False,
            )
        )
        state.rate_limiter = LoginRateLimiter(
            max_failures=s.login_rate_limit_failures,
            window_seconds=s.login_rate_limit_window_seconds,
            cooldown_seconds=s.login_rate_limit_cooldown_seconds,
        )
        state.auth_throughput_limiter = ThroughputLimiter(
            max_attempts=s.auth_rate_limit_attempts,
            window_seconds=s.auth_rate_limit_window_seconds,
        )
        state.oauth_clients = build_client_map(s)
        state.oauth_providers = provider_buttons(state.oauth_clients)

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
