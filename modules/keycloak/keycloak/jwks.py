"""JWKS key cache and JWT validation for Keycloak tokens."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger(__name__)


class JWKSCache:
    """Caches Keycloak's public signing keys and validates JWTs.

    On validation failure with cached keys, refetches JWKS once before
    rejecting -- this handles Keycloak key rotation gracefully.
    """

    def __init__(
        self,
        jwks_url: str,
        ttl_seconds: int = 3600,
        *,
        issuer: str,
        audience: str,
    ) -> None:
        if not issuer:
            raise ValueError("issuer is required for JWT validation")
        if not audience:
            raise ValueError("audience is required for JWT validation")
        self._jwks_url = jwks_url
        self._ttl = ttl_seconds
        self._issuer = issuer
        self._audience = audience
        self._keys: dict[str, Any] = {}
        self._fetched_at: float = 0

    async def validate_jwt(self, token: str) -> dict[str, Any] | None:
        """Decode and validate a JWT. Returns claims dict or None."""
        try:
            unverified = jwt.get_unverified_header(token)
        except jwt.exceptions.DecodeError:
            return None

        kid = unverified.get("kid")
        if kid is None:
            return None

        key = await self._get_key(kid)
        if key is None:
            return None

        return self._decode(token, key)

    def _decode(self, token: str, key: Any) -> dict[str, Any] | None:
        try:
            return jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
            )
        except (
            jwt.ExpiredSignatureError,
            jwt.InvalidIssuerError,
            jwt.InvalidAudienceError,
        ):
            return None
        except jwt.PyJWTError:
            logger.exception("JWT validation failed")
            return None

    async def _get_key(self, kid: str) -> Any | None:
        if self._is_stale() or kid not in self._keys:
            await self._fetch_keys()

        if kid in self._keys:
            return self._keys[kid]

        await self._fetch_keys(force=True)
        return self._keys.get(kid)

    def _is_stale(self) -> bool:
        return time.monotonic() - self._fetched_at > self._ttl

    async def _fetch_keys(self, *, force: bool = False) -> None:
        if not force and not self._is_stale():
            return
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self._jwks_url, timeout=10)
                resp.raise_for_status()
                jwks_data = resp.json()
        except Exception:
            logger.exception("Failed to fetch JWKS from %s", self._jwks_url)
            return

        new_keys: dict[str, Any] = {}
        for key_data in jwks_data.get("keys", []):
            kid = key_data.get("kid")
            if kid and key_data.get("alg") == "RS256":
                try:
                    public_key = RSAAlgorithm.from_jwk(key_data)
                    new_keys[kid] = public_key
                except Exception:
                    logger.warning("Failed to parse JWK kid=%s", kid)
        self._keys = new_keys
        self._fetched_at = time.monotonic()
