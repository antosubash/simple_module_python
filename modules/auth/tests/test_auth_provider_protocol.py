"""Tests for the AuthProvider protocol."""

from __future__ import annotations

from auth.contracts.provider import AuthProvider
from auth.contracts.schemas import UserContext
from starlette.requests import Request


class _FakeProvider:
    """Minimal implementation to verify protocol conformance."""

    name = "fake"

    async def resolve_user(self, request: Request) -> UserContext | None:
        return None

    def get_login_url(self, request: Request, next_url: str | None = None) -> str:
        return "/fake/login"

    def get_logout_url(self, request: Request) -> str:
        return "/fake/logout"

    def get_public_paths(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (("/fake/login",), ())

    def is_bearer_request(self, request: Request) -> bool:
        return False


def test_fake_provider_satisfies_protocol():
    provider = _FakeProvider()
    assert isinstance(provider, AuthProvider)


def test_protocol_rejects_incomplete_implementation():
    class _Incomplete:
        name = "broken"

    assert not isinstance(_Incomplete(), AuthProvider)


def test_auth_package_reexports_auth_provider():
    import auth

    assert hasattr(auth, "AuthProvider")
    assert "AuthProvider" in auth.__all__
    from auth.contracts.provider import AuthProvider as Canonical

    assert auth.AuthProvider is Canonical


def test_contracts_package_reexports_auth_provider():
    from auth.contracts import AuthProvider

    assert AuthProvider is not None
