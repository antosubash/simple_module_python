"""JWKS key cache and JWT validation for OIDC tokens."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from urllib.parse import urlsplit

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger(__name__)
_MIN_REFETCH_INTERVAL_SECONDS = 30


class JWKSCache:
    """Caches OIDC's public signing keys and validates JWTs.

    Unknown keys trigger a refresh, with a per-cache cooldown and lock to
    bound unauthenticated fetches while still discovering key rotation.
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
        self._last_fetch_attempt: float | None = None
        self._fetch_lock = asyncio.Lock()

    async def validate_jwt(
        self,
        token: str,
        *,
        audience: str | None = None,
        trusted_audiences: set[str] | None = None,
    ) -> dict[str, Any] | None:
        """Decode and validate a JWT. Returns claims dict or None."""
        try:
            unverified = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            return None

        kid = unverified.get("kid")
        if not isinstance(kid, str) or not kid:
            return None

        key = await self._get_key(kid)
        if key is None:
            return None

        return self._decode(token, key, audience or self._audience, trusted_audiences or set())

    def _decode(
        self, token: str, key: Any, audience: str, trusted_audiences: set[str]
    ) -> dict[str, Any] | None:
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=audience,
                options={"require": ["iss", "sub", "aud", "exp", "iat"]},
            )
            if not isinstance(claims["sub"], str) or not claims["sub"].strip():
                return None
            if any(type(claims[k]) is not int for k in ("exp", "iat")):
                return None
            audiences = claims["aud"]
            audiences = [audiences] if isinstance(audiences, str) else audiences
            if not isinstance(audiences, list) or any(
                not isinstance(a, str) or not a for a in audiences
            ):
                return None
            if set(audiences) - {audience} - trusted_audiences:
                return None
            azp = claims.get("azp")
            if (len(audiences) > 1 or azp is not None) and azp != self._audience:
                return None
            return claims
        except jwt.PyJWTError:
            logger.debug("OIDC JWT validation failed")
            return None

    async def _get_key(self, kid: str) -> Any | None:
        if self._is_stale() or kid not in self._keys:
            async with self._fetch_lock:
                await self._fetch_keys()
        return self._keys.get(kid)

    def _is_stale(self) -> bool:
        return time.monotonic() - self._fetched_at > self._ttl

    async def _fetch_keys(self) -> None:
        now = time.monotonic()
        if (
            self._last_fetch_attempt is not None
            and now - self._last_fetch_attempt < _MIN_REFETCH_INTERVAL_SECONDS
        ):
            return
        # Failed attempts must also cool down; keep the last good keys on failure.
        self._last_fetch_attempt = now
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self._jwks_url, timeout=10)
                resp.raise_for_status()
                jwks_data = resp.json()
        except Exception:
            logger.warning("Failed to fetch OIDC JWKS")
            return

        new_keys: dict[str, Any] = {}
        if not isinstance(jwks_data, dict) or not isinstance(jwks_data.get("keys"), list):
            return
        for key_data in jwks_data["keys"]:
            if not isinstance(key_data, dict) or not self._is_rsa_signing_key(key_data):
                continue
            key_issuer = key_data.get("issuer", self._issuer)
            if isinstance(key_issuer, str):
                # Entra may template its JWK issuer even on tenant-specific discovery.
                tenant = urlsplit(self._issuer).path.strip("/").split("/")[0]
                key_issuer = key_issuer.replace("{tenantid}", tenant)
            if key_issuer != self._issuer:
                continue
            kid = key_data.get("kid")
            if kid:
                try:
                    public_key = RSAAlgorithm.from_jwk(key_data)
                    new_keys[kid] = public_key
                except Exception:
                    logger.warning("Failed to parse JWK kid=%s", kid)
        if not new_keys:
            return
        self._keys = new_keys
        self._fetched_at = time.monotonic()

    @staticmethod
    def _is_rsa_signing_key(key_data: dict[str, Any]) -> bool:
        """Accept RSA signing keys. ``alg``/``use`` are optional in JWKS — Entra
        omits ``alg`` — so only reject when a present value is incompatible."""
        if (
            not isinstance(key_data.get("kid"), str)
            or not key_data["kid"]
            or key_data.get("kty") != "RSA"
        ):
            return False
        alg = key_data.get("alg")
        if alg and alg != "RS256":
            return False
        use = key_data.get("use")
        if use and use != "sig":
            return False
        operations = key_data.get("key_ops")
        return operations is None or (isinstance(operations, list) and "verify" in operations)
