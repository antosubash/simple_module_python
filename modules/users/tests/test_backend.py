"""Tests for the auth backend builder."""

from __future__ import annotations

from fastapi_users.authentication import AuthenticationBackend, CookieTransport


def test_build_auth_backend_name():
    from users.backend import build_auth_backend, build_cookie_transport

    transport = build_cookie_transport(
        cookie_name="sm_auth",
        cookie_max_age_seconds=86400,
        cookie_secure=False,
        cookie_samesite="lax",
    )
    backend = build_auth_backend(transport)

    assert backend.name == "cookie"


def test_build_auth_backend_is_authentication_backend():
    from users.backend import build_auth_backend, build_cookie_transport

    transport = build_cookie_transport(
        cookie_name="sm_auth",
        cookie_max_age_seconds=86400,
        cookie_secure=False,
        cookie_samesite="lax",
    )
    backend = build_auth_backend(transport)

    assert isinstance(backend, AuthenticationBackend)


def test_build_cookie_transport_sets_name():
    from users.backend import build_cookie_transport

    transport = build_cookie_transport(
        cookie_name="my_cookie",
        cookie_max_age_seconds=3600,
        cookie_secure=True,
        cookie_samesite="strict",
    )

    assert isinstance(transport, CookieTransport)
    assert transport.cookie_name == "my_cookie"
    assert transport.cookie_max_age == 3600
    assert transport.cookie_secure is True


def test_build_auth_backend_strategy_is_database_strategy():
    """The get_strategy callable in the backend is get_database_strategy."""
    from users.backend import build_auth_backend, build_cookie_transport, get_database_strategy

    transport = build_cookie_transport("sm_auth", 86400, False, "lax")
    backend = build_auth_backend(transport)

    # The backend's get_strategy callable should be get_database_strategy
    assert backend.get_strategy is get_database_strategy
