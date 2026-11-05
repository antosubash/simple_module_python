"""Issuer-scoped adapter for shared cache persistence."""

from auth.oidc_common.persistence import upsert_user_cache
from simple_module_db import independent_session
from starlette.requests import Request

from oidc.models import OidcUserCache


class CachePersistence:
    async def _upsert_user_cache(
        self, request: Request, claims: dict, *, throttle_login: bool = False
    ) -> str | None:
        try:
            issuer, subject = self._identity(claims)
        except ValueError:
            return None
        name = self._display_name(claims)
        return await upsert_user_cache(
            request,
            model=OidcUserCache,
            identity={"issuer": issuer, "subject": subject},
            email=self._email(claims),
            name=name,
            update_name=bool(name),
            throttle_login=throttle_login,
            session_factory=independent_session,
        )
