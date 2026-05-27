"""KeycloakAuthProvider — resolves users from Keycloak JWTs or session."""

from __future__ import annotations

from typing import TYPE_CHECKING

from auth.contracts.schemas import UserContext
from starlette.requests import Request

if TYPE_CHECKING:
    from keycloak.settings import KeycloakSettings


class KeycloakAuthProvider:
    """OIDC auth provider backed by Keycloak."""

    name = "keycloak"
    _is_auth_provider = True

    def __init__(self, settings: KeycloakSettings | None = None) -> None:
        self._settings = settings
        self.jwks_cache = None

    async def resolve_user(self, request: Request) -> UserContext | None:
        return None

    def get_login_url(
        self, request: Request | None, next_url: str | None = None
    ) -> str:
        return "/keycloak/login"

    def get_logout_url(self, request: Request | None) -> str:
        return "/keycloak/logout"

    def get_public_paths(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (
            ("/keycloak/login", "/keycloak/logout", "/api/keycloak/auth/"),
            (),
        )

    def is_bearer_request(self, request: Request | None) -> bool:
        if request is None:
            return False
        return request.headers.get("authorization", "").startswith("Bearer ")
