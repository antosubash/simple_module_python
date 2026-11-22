"""Shared public-route decisions."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from simple_module_core.web.public_routes import PublicRouteRegistry
from simple_module_hosting._route_access import is_public_operation
from simple_module_hosting.public_access import is_public


def test_registry_is_method_aware_and_skips_provider() -> None:
    class UnexpectedProvider:
        def get_public_paths(self):
            pytest.fail("Public access must not consult the provider")

    app = FastAPI()
    registry = PublicRouteRegistry()
    registry.add_exact("/api/public", methods={"GET"})
    app.state.public_routes = registry
    app.state.auth = SimpleNamespace(auth_provider=UnexpectedProvider())
    assert is_public(app, "GET", "/api/public")
    app.state.auth.auth_provider = None
    assert not is_public(app, "POST", "/api/public")
    assert not is_public(app, "GET", "/api/private")


@pytest.mark.parametrize("operation", [False, True])
def test_legacy_provider_cannot_open_unregistered_paths(operation: bool) -> None:
    class LegacyProvider:
        def get_public_paths(self):
            return ("/legacy/",), ("/login",)

    app = FastAPI()
    app.state.auth = SimpleNamespace(auth_provider=LegacyProvider())
    check = is_public_operation if operation else is_public
    assert not check(app, "GET", "/legacy/item")
    assert not check(app, "POST", "/login")


def test_operation_keeps_placeholder_substitution() -> None:
    app = FastAPI()
    registry = PublicRouteRegistry()
    registry.add_regex(r"/api/items/\d+$", methods={"GET"})
    app.state.public_routes = registry
    assert is_public_operation(app, "GET", "/api/items/{id}")
    assert not is_public_operation(app, "POST", "/api/items/{id}")


def test_missing_registry_and_provider_is_private() -> None:
    assert not is_public(FastAPI(), "GET", "/api/private")
