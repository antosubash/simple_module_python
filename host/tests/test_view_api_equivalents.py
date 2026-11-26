"""Every non-GET view route says which ``/api`` route does the same, or why none may.

A page refuses API tokens, so a change a browser can make through a view form
must also be reachable through the token-admitting JSON API (the project CLI
drives the API only). Each non-GET route outside ``/api/`` therefore carries at
least one ``api_equivalent(...)`` (one per scope) or exactly one
``api_exempt(...)``; every equivalent must name a registered ``/api`` operation,
by method and exact path template, that admits tokens
(``simple_module_hosting.auth.api_equivalent``).

Each app is built the way ``host/main.py`` builds production (the same host
routers), once per auth provider: Keycloak and OIDC replace ``Users``. Routes
mount at construction, so no lifespan is needed.
"""

from __future__ import annotations

import pytest
from fastapi.routing import iter_route_contexts
from simple_module_core.modules.discovery import discover_modules
from simple_module_hosting.auth.api_equivalent import (
    ApiEquivalent,
    dependant_api_declarations,
    view_route_offenders,
)
from simple_module_hosting.boot.app_builder import create_app
from simple_module_hosting.boot.host import _resolve_routers
from simple_module_hosting.config.settings import Settings

from host.routes import HOST_ROUTERS

_USERS = "Users"


def _build(provider: str):
    modules = None
    if provider != "users":
        modules = [
            m.meta.name
            for m in discover_modules()
            if m.meta.name != _USERS and _USERS not in m.meta.depends_on
        ]
    return create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            environment="testing",
            secret_key="test-secret-key-view-api-equivalents",
            multi_tenant=True,
            auth_provider=provider,
            modules_enabled=modules,
        ),
        routers=_resolve_routers(HOST_ROUTERS),
    )


@pytest.mark.parametrize("provider", ["users", "keycloak", "oidc"])
def test_every_mutating_view_route_is_declared(provider: str):
    offenders = view_route_offenders(_build(provider))
    assert not offenders, "\n".join(offenders)


@pytest.mark.parametrize("action", ["toggle", "clear"])
def test_feature_flag_actions_declare_system_and_tenant_targets(action: str):
    path = f"/admin/feature-flags/{{name}}/{action}"
    ctx = next(c for c in iter_route_contexts(_build("users").routes) if c.path == path)
    targets = {d.path for d in dependant_api_declarations(ctx.dependant)}
    assert targets == {
        "/api/feature_flags/{name}",
        "/api/feature_flags/tenant/{tenant_id}/{name}",
    }
    assert all(isinstance(d, ApiEquivalent) for d in dependant_api_declarations(ctx.dependant))
