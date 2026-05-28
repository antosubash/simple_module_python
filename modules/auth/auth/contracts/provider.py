"""AuthProvider protocol — the contract both users and keycloak modules implement."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from starlette.requests import Request

from auth.contracts.schemas import UserContext


@runtime_checkable
class AuthProvider(Protocol):
    """Extension point for swappable authentication backends.

    Exactly one module (``users`` or ``keycloak``) registers an implementation
    on ``app.state.auth.auth_provider`` during ``register_settings``.
    The ``AuthMiddleware`` delegates to it on every request.
    """

    name: str

    async def resolve_user(self, request: Request) -> UserContext | None: ...

    def get_login_url(self, request: Request, next_url: str | None = None) -> str: ...

    def get_logout_url(self, request: Request) -> str: ...

    def get_public_paths(self) -> tuple[tuple[str, ...], tuple[str, ...]]: ...

    def is_bearer_request(self, request: Request) -> bool: ...


__all__ = ["AuthProvider"]
