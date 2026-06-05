"""OIDC client -- authorization URL, code exchange, and logout.

Endpoint-driven: the authorize/token/end-session URLs come from the discovery
document, so this client is provider-agnostic.
"""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

import httpx


class OIDCClient:
    """Thin wrapper around a provider's discovered OIDC endpoints."""

    def __init__(
        self,
        *,
        authorization_endpoint: str,
        token_endpoint: str,
        end_session_endpoint: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        self._authorization_endpoint = authorization_endpoint
        self._token_endpoint = token_endpoint
        self._end_session_endpoint = end_session_endpoint
        self._client_id = client_id
        self._client_secret = client_secret

    @property
    def token_endpoint(self) -> str:
        return self._token_endpoint

    def build_authorization_url(
        self,
        redirect_uri: str,
        nonce: str,
        scope: str = "openid email profile",
    ) -> tuple[str, str]:
        state = secrets.token_urlsafe(32)
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
            "nonce": nonce,
        }
        url = f"{self._authorization_endpoint}?{urlencode(params)}"
        return url, state

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(self._token_endpoint, data=data, timeout=10)
            resp.raise_for_status()
            return resp.json()

    def build_logout_url(
        self,
        post_logout_redirect_uri: str,
        id_token_hint: str | None = None,
    ) -> str:
        """End-session URL. Falls back to the local redirect if the provider
        does not advertise an ``end_session_endpoint``."""
        if not self._end_session_endpoint:
            return post_logout_redirect_uri
        params: dict[str, str] = {"post_logout_redirect_uri": post_logout_redirect_uri}
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        return f"{self._end_session_endpoint}?{urlencode(params)}"
