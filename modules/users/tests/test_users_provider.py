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


def test_public_paths():
    provider = UsersAuthProvider()
    prefixes, exact = provider.get_public_paths()
    assert "/users/login" in prefixes
    assert "/api/users/auth/" in prefixes


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
