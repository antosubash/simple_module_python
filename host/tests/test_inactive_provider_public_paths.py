"""An inactive auth provider contributes no public paths.

``select_auth_provider`` drops every provider but the configured one from the
loaded module list, so the dropped module's ``register_public_routes`` never
runs. Public prefixes are therefore effectively gated on being the *active*
provider, exactly like the old ``get_public_paths`` (only the active provider's
was consulted).
"""

from __future__ import annotations

from keycloak.constants import PUBLIC_PATH_PREFIXES as KEYCLOAK_PREFIXES
from keycloak.module import KeycloakModule
from simple_module_core.discovery import select_auth_provider
from simple_module_core.public_routes import PublicRouteRegistry
from users.constants import PUBLIC_PATH_PREFIXES as USERS_PREFIXES
from users.module import UsersModule


def _registry_for(preferred: str) -> PublicRouteRegistry:
    registry = PublicRouteRegistry()
    for module in select_auth_provider([UsersModule(), KeycloakModule()], preferred):
        module.register_public_routes(registry)
    return registry


def _exposes(registry: PublicRouteRegistry, prefixes: tuple[str, ...]) -> bool:
    return any(registry.matches("GET", p) for p in prefixes)


def test_users_active_does_not_expose_keycloak_paths() -> None:
    registry = _registry_for("users")
    assert _exposes(registry, USERS_PREFIXES)
    assert not _exposes(registry, KEYCLOAK_PREFIXES)


def test_keycloak_active_does_not_expose_users_paths() -> None:
    registry = _registry_for("keycloak")
    assert _exposes(registry, KEYCLOAK_PREFIXES)
    assert not _exposes(registry, USERS_PREFIXES)
