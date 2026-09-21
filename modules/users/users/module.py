"""Users module — local-account authentication and user management."""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from simple_module_core.audit_links import AuditLinkRegistry
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry
from simple_module_core.setup_steps import SetupRegistry

from users.constants import (
    ADMIN_ROLE_NAME,
    PERM_USERS_MANAGE,
    PERM_USERS_SELF_PROFILE,
    USER_ROLE_NAME,
)

if TYPE_CHECKING:
    from fastapi import FastAPI
    from simple_module_core.events import EventBus
    from simple_module_core.invalidation import InvalidationBus

_MODULE_DEPENDENCY_AUTH = "Auth"
# register_settings() goes through settings.registration.register_module_settings,
# which reads app.state.settings — so Settings must register first.
_MODULE_DEPENDENCY_SETTINGS = "Settings"

# Menu URLs
_URL_USERS_ADMIN = "/admin/users/"
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
        # Sign-in and self-service stay on /users; the management CRUD
        # belongs with the other admin screens. One view_prefix cannot
        # express both, hence the second router.
        admin_view_prefix="/admin/users",
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
            # Same reason: turning demo mode on from the settings UI has to
            # seed the accounts and refresh the cached ids, or the buttons
            # appear on a sign-in page that 404s until the next restart.
            from users.demo import ensure_demo_users

            await ensure_demo_users(app)

        bus.subscribe(settings_reloaded, _rebuild_oauth_clients)

    def register_invalidations(self, bus: InvalidationBus, app: FastAPI) -> None:
        """Let another worker's revocation drop this worker's cached counter.

        ``_version_still_current`` runs on nearly every authenticated request, so
        the stored ``session_version`` is cached per process. Without this the
        cache is the reason a password change made because an account is
        believed compromised leaves the *other* workers admitting the old
        sessions for the rest of their TTL (GH #318).
        """
        from users.session_revocation import subscribe

        subscribe(bus)

    def register_middleware(self, app: FastAPI) -> None:
        """Refuse writes from either shared demo session.

        A no-op until ``demo_mode`` and ``demo_read_only`` are both on — it
        re-reads them per request — so an install that never hosts a demo pays
        one frozenset lookup on unsafe methods and nothing on reads.
        """
        from users.demo_guard import DemoReadOnlyMiddleware

        app.add_middleware(DemoReadOnlyMiddleware)

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            "Users",
            [PERM_USERS_MANAGE, PERM_USERS_SELF_PROFILE],
        )
        registry.map_role(USER_ROLE_NAME, [PERM_USERS_SELF_PROFILE])

    def register_setup_steps(self, registry: SetupRegistry) -> None:
        """Gate the app until an administrator exists — see ``users.setup``."""
        from users.setup import build_admin_step

        registry.add(build_admin_step())

    def register_audit_links(self, registry: AuditLinkRegistry) -> None:
        # Built in users.audit: the link now carries a batch resolver that
        # names each row (full_name, or the email while an invite is
        # outstanding), which is a query and does not belong in a hook file.
        from users.audit import build_user_audit_link

        registry.register(build_user_audit_link(_URL_USERS_ADMIN))

    def register_menu_items(self, registry: MenuRegistry) -> None:
        # Admin-only user management
        registry.add(
            MenuItem(
                label="Users",
                label_key="users.nav.users",
                url=_URL_USERS_ADMIN,
                icon=_ICON_USERS,
                order=100,
                section=MenuSection.ADMIN_SIDEBAR,
                roles=[ADMIN_ROLE_NAME],
                group="Access",
                group_key="ui.nav_groups.access",
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
        from users.auth_local import api as auth_local_api
        from users.auth_local.demo_api import router as demo_router
        from users.auth_local.token_api import router as token_router
        from users.auth_local.views import router as auth_views
        from users.contracts.schemas import UserCreate, UserRead
        from users.deps import fastapi_users
        from users.oauth.api import register_oauth_routes

        api_router.include_router(auth_local_api.router)
        api_router.include_router(demo_router)
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

    def register_admin_routes(self, admin_router: APIRouter) -> None:
        from users.admin.views import router as admin_views

        admin_router.include_router(admin_views)

    async def on_startup(self, app: FastAPI) -> None:
        """Build the mailer, limiters, OAuth clients and the seeded admin.

        The body lives in ``users.startup``: every step reads a DB-hydrated
        setting, so it must run after the lifespan's hydration, and keeping it
        out of this file keeps that boundary visible.
        """
        from users.startup import run_startup

        await run_startup(self, app)
