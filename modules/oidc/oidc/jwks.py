"""JWKS key cache and JWT validation for OIDC tokens."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger(__name__)


class JWKSCache:
    """Caches a provider's public signing keys and validates JWTs.

    On validation failure with cached keys, refetches JWKS once before
    rejecting -- this handles signing-key rotation gracefully.
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
            if not self._is_rsa_signing_key(key_data):
                continue
            kid = key_data["kid"]
            try:
                new_keys[kid] = RSAAlgorithm.from_jwk(key_data)
            except Exception:
                logger.warning("Failed to parse JWK kid=%s", kid)
        self._keys = new_keys
        self._fetched_at = time.monotonic()

    @staticmethod
    def _is_rsa_signing_key(key_data: dict[str, Any]) -> bool:
        """Accept RSA signing keys. ``alg``/``use`` are optional in JWKS — Entra
        omits ``alg`` — so only reject when a present value is incompatible."""
        if not key_data.get("kid") or key_data.get("kty") != "RSA":
            return False
        alg = key_data.get("alg")
        if alg and alg != "RS256":
            return False
        use = key_data.get("use")
        return not (use and use != "sig")
