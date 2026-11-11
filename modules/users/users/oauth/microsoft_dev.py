"""Microsoft sign-in against a local IdP, for development and tests only (#879).

With ``oauth_microsoft_discovery_url`` set and ``SM_ENVIRONMENT`` development or
testing, the Microsoft provider takes its endpoints, JWKS and issuer from that
discovery document (a Keycloak realm emitting Entra-shaped claims, say) instead
of ``login.microsoftonline.com``. Every ID-token rule of :class:`MicrosoftOidc`
still applies, with the document's issuer in place of Entra's per-tenant one.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from auth.oidc_common.jwks import JWKSCache

from users.oauth.microsoft import IdTokenError, MicrosoftOidc

_REQUIRED = ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri")
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _allowed_url(url: str) -> bool:
    """HTTPS, or plain HTTP to this machine (a local Keycloak), without credentials."""
    parts = urlsplit(url)
    if not parts.hostname or parts.username or parts.password or "{" in url:
        return False
    return parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS)


class MicrosoftDevOidc(MicrosoftOidc):
    """:class:`MicrosoftOidc` whose endpoints come from a discovery document."""

    def __init__(self, client_id: str, client_secret: str, tenant: str, discovery_url: str) -> None:
        super().__init__(client_id, client_secret, tenant)
        self.discovery_url = discovery_url
        self._jwks: JWKSCache | None = None
        self._lock = asyncio.Lock()

    async def get_authorization_url(
        self,
        redirect_uri: str,
        state: str | None = None,
        scope: list[str] | None = None,
        code_challenge: str | None = None,
        code_challenge_method: Literal["plain", "S256"] | None = None,
        extras_params: dict[str, Any] | None = None,
    ) -> str:
        await self._discover()
        return await super().get_authorization_url(
            redirect_uri,
            state,
            scope,
            code_challenge,
            code_challenge_method,
            extras_params,
        )

    async def get_access_token(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ):
        await self._discover()
        return await super().get_access_token(code, redirect_uri, code_verifier)

    def _cache(self, tid: str) -> JWKSCache:
        if self._jwks is None:  # identity() runs after get_access_token
            raise IdTokenError("discovery document not loaded")
        return self._jwks

    async def _discover(self) -> None:
        """Fetch the document once, on first use: never at boot or settings reload."""
        if not _allowed_url(self.discovery_url):
            raise IdTokenError("discovery URL must be HTTPS or a loopback HTTP address")
        if self._jwks is not None:
            return
        async with self._lock:
            if self._jwks is not None:
                return
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(self.discovery_url, timeout=10)
                    response.raise_for_status()
                    doc = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise IdTokenError(f"discovery failed: {exc}") from exc
            if not isinstance(doc, dict) or not all(
                isinstance(doc.get(key), str) and _allowed_url(doc[key]) for key in _REQUIRED
            ):
                raise IdTokenError("discovery document lacks usable issuer or endpoints")
            self.authorize_endpoint = doc["authorization_endpoint"]
            self.access_token_endpoint = doc["token_endpoint"]
            self.refresh_token_endpoint = doc["token_endpoint"]
            self._jwks = JWKSCache(doc["jwks_uri"], issuer=doc["issuer"], audience=self.client_id)
