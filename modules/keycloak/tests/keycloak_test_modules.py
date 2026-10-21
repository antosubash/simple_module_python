"""The module set a Keycloak test app boots with.

Selecting ``keycloak`` drops ``Users``, and outside development a module whose
``depends_on`` is not loaded refuses to boot (GH #501). ``permissions`` (role
pages) still depends on ``Users``, so a Keycloak install leaves it out — and so
do these tests, rather than booting in a lenient mode production never uses.
"""

from __future__ import annotations

from simple_module_core.discovery import discover_modules

_USERS = "Users"


def keycloak_modules_enabled() -> list[str]:
    """Every installed module except those that need ``Users``."""
    return [m.meta.name for m in discover_modules() if _USERS not in m.meta.depends_on]
