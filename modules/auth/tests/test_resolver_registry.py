"""Tests for the auth.contracts.resolver type + AuthState registry."""

from __future__ import annotations

from collections.abc import Awaitable

from auth.contracts.resolver import PrincipalResolver
from auth.contracts.schemas import UserContext
from starlette.requests import Request


def test_principal_resolver_type_accepts_async_callable():
    """A typical resolver signature should satisfy the type alias at runtime.

    The alias is documentation + a checkable shape — we exercise the shape
    by constructing one and asserting it's a Callable that returns an
    awaitable.
    """

    async def fake_resolver(request: Request) -> UserContext | None:
        return None

    # Runtime — alias resolves to Callable[..., Awaitable[...]]
    resolver: PrincipalResolver = fake_resolver
    assert callable(resolver)
    # Sanity: the function actually returns an awaitable when called.
    from unittest.mock import MagicMock

    result = resolver(MagicMock(spec=Request))
    assert isinstance(result, Awaitable)
    result.close()  # don't leave an unawaited coroutine


def test_auth_state_initializes_with_empty_resolvers():
    from auth.state import AuthState

    state = AuthState()
    assert state.principal_resolvers == []


def test_auth_state_resolvers_is_mutable_list():
    """Modules register resolvers by appending; the list must be a list, not a tuple."""
    from auth.state import AuthState

    state = AuthState()

    async def resolver(request):  # pragma: no cover - registration smoke only
        return None

    state.principal_resolvers.append(resolver)
    assert state.principal_resolvers == [resolver]


def test_auth_module_register_settings_populates_app_state():
    """``AuthModule.register_settings(app)`` must put an AuthState on ``app.state.auth``."""
    from fastapi import FastAPI

    from auth.module import AuthModule
    from auth.state import AuthState

    app = FastAPI()
    AuthModule().register_settings(app)

    assert isinstance(app.state.auth, AuthState)
    assert app.state.auth.principal_resolvers == []


def test_auth_package_reexports_public_surface():
    """Downstream authors should be able to ``from auth import PrincipalResolver, UserContext``."""
    import auth

    assert hasattr(auth, "PrincipalResolver")
    assert hasattr(auth, "UserContext")
    assert "PrincipalResolver" in auth.__all__
    assert "UserContext" in auth.__all__

    # Identity check — re-exports point at the canonical definitions.
    from auth.contracts.resolver import PrincipalResolver
    from auth.contracts.schemas import UserContext

    assert auth.PrincipalResolver is PrincipalResolver
    assert auth.UserContext is UserContext
