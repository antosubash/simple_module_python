"""Smoke tests for the deps module public API."""

from __future__ import annotations

from fastapi_users import FastAPIUsers
from fastapi_users.authentication import AuthenticationBackend


def test_auth_backend_import():
    from users.deps import auth_backend

    assert isinstance(auth_backend, AuthenticationBackend)


def test_auth_backend_name():
    from users.deps import auth_backend

    assert auth_backend.name == "cookie"


def test_fastapi_users_import():
    from users.deps import fastapi_users

    assert isinstance(fastapi_users, FastAPIUsers)


def test_current_active_user_is_callable():
    from users.deps import current_active_user

    assert callable(current_active_user)


def test_current_superuser_is_callable():
    from users.deps import current_superuser

    assert callable(current_superuser)


def test_get_user_manager_is_callable():
    from users.deps import get_user_manager

    assert callable(get_user_manager)


def test_get_user_db_is_callable():
    from users.deps import get_user_db

    assert callable(get_user_db)


def test_get_access_token_db_is_callable():
    from users.deps import get_access_token_db

    assert callable(get_access_token_db)


def test_all_exports_present():
    """Verify all listed __all__ members are importable from users.deps."""
    import users.deps as deps

    for name in deps.__all__:
        assert hasattr(deps, name), f"Missing export: {name}"
