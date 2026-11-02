"""The wizard's anonymous-access rule, on the surface that actually grants it.

``SetupMiddleware``'s exemption list decides whether a request is *redirected*;
``attach_public_routes`` decides whether it is *authenticated*. Only the second
is an auth bypass when it matches too loosely, and it is the one this file
covers — ``test_setup_gate`` exercises the middleware's own tuples and cannot
speak for this side.

The bug being pinned: registering a bare ``/setup`` prefix also hands anonymous
access to any unrelated route that merely starts with those six characters.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from simple_module_core.public_routes import PublicRouteRegistry
from simple_module_hosting._phase_helpers import attach_public_routes


def _registry_after_attach(public_paths: list[str] | None = None) -> PublicRouteRegistry:
    registry = PublicRouteRegistry()
    app = SimpleNamespace(state=SimpleNamespace())
    settings = SimpleNamespace(auth_public_paths=public_paths or [])
    attach_public_routes(app, settings, registry)
    return registry


@pytest.mark.parametrize(
    "path,public",
    [
        ("/setup", True),
        ("/setup/", True),
        ("/setup/administrator", True),
        ("/setup/test-connections", True),
        # The bypass. A module owning "/setup-guide" never asked to be public,
        # and a bare-prefix rule would have made it so.
        ("/setup-guide", False),
        ("/setupadmin", False),
        ("/setup-wizard/secrets", False),
        ("/dashboard", False),
    ],
)
def test_only_the_wizard_is_anonymous(path: str, public: bool) -> None:
    registry = _registry_after_attach()

    assert registry.matches("GET", path) is public, (
        f"{path} anonymous={registry.matches('GET', path)}, expected {public}"
    )


def test_the_exemption_covers_every_method() -> None:
    """The wizard POSTs to create the administrator and run migrations, so a
    GET-only rule would leave those authenticated and unreachable."""
    registry = _registry_after_attach()

    for method in ("GET", "POST", "PUT", "DELETE"):
        assert registry.matches(method, "/setup/administrator") is True


def test_host_configured_public_paths_are_still_honoured() -> None:
    """The SM_AUTH_PUBLIC_PATHS escape hatch must survive alongside the
    wizard's own rule."""
    registry = _registry_after_attach(["/status"])

    assert registry.matches("GET", "/status") is True
    assert registry.matches("GET", "/setup") is True
