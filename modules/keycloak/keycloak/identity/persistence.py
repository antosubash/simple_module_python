"""Subject-scoped adapter for shared cache persistence."""

from auth.oidc_common.persistence import upsert_user_cache
from starlette.requests import Request

from keycloak.models import KeycloakUserCache


class CachePersistence:
    async def _upsert_user_cache(
        self, request: Request, claims: dict, *, throttle_login: bool = False
    ) -> str:
        result = await upsert_user_cache(
            request,
            model=KeycloakUserCache,
            identity={"keycloak_sub": claims["sub"]},
            email=claims.get("email"),
            name=claims.get("preferred_username"),
            throttle_login=throttle_login,
            update_name="preferred_username" in claims,
        )
        return result if result is not None else claims.get("sub", "unknown")
