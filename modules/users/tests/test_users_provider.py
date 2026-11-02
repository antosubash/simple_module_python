"""Tests for UsersAuthProvider."""

from __future__ import annotations

from auth.contracts.provider import AuthProvider
from users.provider import UsersAuthProvider


def test_users_provider_satisfies_protocol():
    provider = UsersAuthProvider()
    assert isinstance(provider, AuthProvider)


def test_login_url():
    provider = UsersAuthProvider()
    assert provider.get_login_url(None) == "/users/login"


def test_logout_url():
    provider = UsersAuthProvider()
    assert provider.get_logout_url(None) == "/users/logout"


def test_public_paths_come_from_the_registry():
    from simple_module_core.public_routes import PublicRouteRegistry
    from users.module import UsersModule

    registry = PublicRouteRegistry()
    UsersModule().register_public_routes(registry)
    assert registry.matches("GET", "/users/login")
    assert registry.matches("POST", "/api/users/auth/login")
    assert not registry.matches("GET", "/users/admin")
    assert not hasattr(UsersAuthProvider(), "get_public_paths")


def test_is_bearer_request_true():
    from unittest.mock import MagicMock

    request = MagicMock()
    request.headers = {"authorization": "Bearer abc123"}
    provider = UsersAuthProvider()
    assert provider.is_bearer_request(request) is True


def test_is_bearer_request_false():
    from unittest.mock import MagicMock

    request = MagicMock()
    request.headers = {}
    provider = UsersAuthProvider()
    assert provider.is_bearer_request(request) is False
