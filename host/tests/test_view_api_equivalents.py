"""Every non-GET view route says which ``/api`` route does the same, or why none may.

A page refuses API tokens, so a change a browser can make through a view form
must also be reachable through the token-admitting JSON API (the project CLI
drives the API only). Each non-GET route outside ``/api/`` therefore carries
exactly one ``api_equivalent(...)`` or ``api_exempt(...)`` dependency; an
equivalent must name a registered ``/api`` operation, by method and exact path
template, that admits tokens (``simple_module_hosting.auth.api_equivalent``).

The users-selected app is the ``app`` fixture; Keycloak and OIDC replace
``Users``, so their routes are walked on apps built for them (routes mount at
construction, so no lifespan is needed).
"""

from __future__ import annotations

import pytest
from simple_module_core.modules.discovery import discover_modules
from simple_module_hosting.auth.api_equivalent import view_route_offenders
from simple_module_hosting.boot.app_builder import create_app
from simple_module_hosting.config.settings import Settings

_USERS = "Users"


def test_users_app_declares_every_mutating_view_route(app):
    offenders = view_route_offenders(app)
    assert not offenders, "\n".join(offenders)


@pytest.mark.parametrize("provider", ["keycloak", "oidc"])
def test_identity_provider_app_declares_every_mutating_view_route(provider: str):
    modules = [
        m.meta.name
        for m in discover_modules()
        if m.meta.name != _USERS and _USERS not in m.meta.depends_on
    ]
    app = create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            environment="testing",
            secret_key="test-secret-key-view-api-equivalents",
            multi_tenant=True,
            auth_provider=provider,
            modules_enabled=modules,
        )
    )
    offenders = view_route_offenders(app)
    assert not offenders, "\n".join(offenders)
