"""OIDC helpers for Keycloak -- authorization URL, token exchange, logout."""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

import httpx


class OIDCClient:
    """Thin wrapper around Keycloak's OIDC endpoints."""

    def __init__(
        self,
        server_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        self._base = (
            f"{server_url.rstrip('/')}/realms/{realm}"
            "/protocol/openid-connect"
        )
        self._client_id = client_id
        self._client_secret = client_secret
        self._server_url = server_url.rstrip("/")
        self._realm = realm

    @property
    def issuer(self) -> str:
        return f"{self._server_url}/realms/{self._realm}"

    @property
    def token_endpoint(self) -> str:
        return f"{self._base}/token"

    @property
    def jwks_url(self) -> str:
        return f"{self._base}/certs"

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
        url = f"{self._base}/auth?{urlencode(params)}"
        return url, state

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_endpoint, data=data, timeout=10
            )
            resp.raise_for_status()
            return resp.json()

    def build_logout_url(
        self,
        post_logout_redirect_uri: str,
        id_token_hint: str | None = None,
    ) -> str:
        params: dict[str, str] = {
            "post_logout_redirect_uri": post_logout_redirect_uri,
        }
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        return f"{self._base}/logout?{urlencode(params)}"
