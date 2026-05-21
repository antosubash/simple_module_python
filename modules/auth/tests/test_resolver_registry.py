"""Tests for the auth.contracts.resolver type + AuthState registry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

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
