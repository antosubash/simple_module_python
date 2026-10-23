"""Shared public-route decisions and legacy-provider failure reporting."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from simple_module_core.public_routes import PublicRouteRegistry
from simple_module_hosting import public_access
from simple_module_hosting._route_access import is_public_operation
from simple_module_hosting.public_access import is_public


def test_registry_is_method_aware_and_skips_provider() -> None:
    class UnexpectedProvider:
        def get_public_paths(self):
            pytest.fail("Registry hits must not consult the legacy provider")

    app = FastAPI()
    registry = PublicRouteRegistry()
    registry.add_exact("/api/public", methods={"GET"})
    app.state.public_routes = registry
    app.state.auth = SimpleNamespace(auth_provider=UnexpectedProvider())
    assert is_public(app, "GET", "/api/public")
    app.state.auth.auth_provider = None
    assert not is_public(app, "POST", "/api/public")
    assert not is_public(app, "GET", "/api/private")


def test_legacy_prefix_and_exact_paths_warn_once() -> None:
    class LegacyProvider:
        def get_public_paths(self):
            return ("/legacy/",), ("/login",)

    app = FastAPI()
    app.state.auth = SimpleNamespace(auth_provider=LegacyProvider())
    with pytest.warns(DeprecationWarning, match="get_public_paths") as warnings:
        assert is_public(app, "GET", "/legacy/item")
        assert is_public(app, "POST", "/login")
        assert not is_public(app, "GET", "/login-extra")
    assert len(warnings) == 1


@pytest.mark.parametrize("operation", [False, True])
def test_raising_legacy_provider_is_logged(caplog, monkeypatch, operation: bool) -> None:
    monkeypatch.setattr(public_access, "_provider_failure_warned", False)

    class RaisingProvider:
        def get_public_paths(self):
            raise RuntimeError("provider failed")

    app = FastAPI()
    app.state.auth = SimpleNamespace(auth_provider=RaisingProvider())
    check = is_public_operation if operation else is_public
    with pytest.warns(DeprecationWarning, match="get_public_paths"):
        assert not check(app, "GET", "/api/private/{id}")
    assert "Auth provider failed to report public paths" in caplog.text
    assert "provider failed" in caplog.text


def test_operation_keeps_placeholder_substitution() -> None:
    app = FastAPI()
    registry = PublicRouteRegistry()
    registry.add_regex(r"/api/items/\d+$", methods={"GET"})
    app.state.public_routes = registry
    assert is_public_operation(app, "GET", "/api/items/{id}")
    assert not is_public_operation(app, "POST", "/api/items/{id}")


def test_missing_registry_and_provider_is_private() -> None:
    assert not is_public(FastAPI(), "GET", "/api/private")
