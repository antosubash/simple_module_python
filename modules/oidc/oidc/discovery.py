"""Validated OIDC discovery metadata; endpoint hosts may legitimately differ."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx


def _validate_url(value: object, *, development: bool) -> str:
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        raise ValueError("OIDC metadata URL must be a non-empty URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ({"https", "http"} if development else {"https"})
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("OIDC metadata requires HTTPS URLs without credentials or fragments")
    return value


@dataclass(frozen=True)
class OidcMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    end_session_endpoint: str = ""
    revocation_endpoint: str = ""
    token_endpoint_auth_methods_supported: list[str] | None = None

    @classmethod
    def from_document(
        cls, doc: dict, *, expected_issuer: str | None = None, development: bool = False
    ) -> OidcMetadata:
        if not isinstance(doc, dict):
            raise ValueError("OIDC discovery document must be an object")
        required = ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri")
        missing = [key for key in required if not doc.get(key)]
        if missing:
            raise ValueError(
                f"OIDC discovery document missing required fields: {', '.join(missing)}"
            )
        values = {key: _validate_url(doc[key], development=development) for key in required}
        issuer = urlsplit(values["issuer"])
        if issuer.query or "{" in values["issuer"] or "}" in values["issuer"]:
            raise ValueError("OIDC issuer must be concrete and have no query")
        # Compared without one trailing slash: issuers such as Auth0's end in
        # "/" while the discovery URL is built without it. Tokens are still
        # validated against the issuer exactly as the document states it.
        if expected_issuer is not None and values["issuer"].rstrip("/") != expected_issuer.rstrip(
            "/"
        ):
            raise ValueError("OIDC discovery issuer does not match configured issuer")
        for key in ("end_session_endpoint", "revocation_endpoint"):
            value = doc.get(key, "")
            values[key] = _validate_url(value, development=development) if value != "" else ""
        methods = doc.get("token_endpoint_auth_methods_supported")
        if "token_endpoint_auth_methods_supported" in doc and (
            not isinstance(methods, list) or not all(isinstance(m, str) for m in methods)
        ):
            raise ValueError("OIDC token endpoint auth methods must be a list of strings")
        return cls(**values, token_endpoint_auth_methods_supported=methods)


async def fetch_metadata(
    discovery_url: str, *, expected_issuer: str | None = None, development: bool = False
) -> OidcMetadata:
    _validate_url(discovery_url, development=development)
    async with httpx.AsyncClient() as client:
        resp = await client.get(discovery_url, timeout=10)
        resp.raise_for_status()
        return OidcMetadata.from_document(
            resp.json(), expected_issuer=expected_issuer, development=development
        )
