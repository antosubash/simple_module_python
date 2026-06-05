"""OIDC discovery -- fetch and parse ``.well-known/openid-configuration``.

Resolved once at startup; the returned endpoints drive the OIDC client and the
JWKS validator, so per-provider URL templates are never hardcoded.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class OidcMetadata:
    """The subset of OIDC provider metadata this module relies on."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    end_session_endpoint: str = ""

    @classmethod
    def from_document(cls, doc: dict) -> OidcMetadata:
        """Build metadata from a parsed discovery document.

        Raises ``ValueError`` if a required endpoint is absent.
        """
        required = ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri")
        missing = [k for k in required if not doc.get(k)]
        if missing:
            msg = f"OIDC discovery document missing required fields: {', '.join(missing)}"
            raise ValueError(msg)
        return cls(
            issuer=doc["issuer"],
            authorization_endpoint=doc["authorization_endpoint"],
            token_endpoint=doc["token_endpoint"],
            jwks_uri=doc["jwks_uri"],
            end_session_endpoint=doc.get("end_session_endpoint", ""),
        )


async def fetch_metadata(discovery_url: str) -> OidcMetadata:
    """Fetch and parse the provider's OIDC discovery document."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(discovery_url, timeout=10)
        resp.raise_for_status()
        return OidcMetadata.from_document(resp.json())
