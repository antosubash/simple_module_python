"""Subject-scoped adapter for shared cache persistence."""

from auth.oidc_common.persistence import upsert_user_cache
from starlette.requests import Request

from keycloak.models import KeycloakUserCache


class CachePersistence:
    async def _upsert_user_cache(
        self, request: Request, claims: dict, *, throttle_login: bool = False
    ) -> str:
        name = claims.get("preferred_username")
        valid_name = name is None or isinstance(name, str)
        result = await upsert_user_cache(
            request,
            model=KeycloakUserCache,
            identity={"keycloak_sub": claims["sub"]},
            email=claims.get("email"),
            name=name if valid_name else None,
            throttle_login=throttle_login,
            update_name="preferred_username" in claims and valid_name,
        )
        return result if result is not None else claims.get("sub", "unknown")
