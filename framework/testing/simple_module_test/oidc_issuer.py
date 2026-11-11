"""An in-process OpenID Connect issuer for tests: a signing key, JWKS and discovery.

Lets a module test an OIDC sign-in end to end without a real IdP (#879)::

    issuer = OidcTestIssuer("https://idp.test/tenant/v2.0")
    httpx_mock.add_response(url=issuer.discovery_url, json=issuer.discovery())
    httpx_mock.add_response(url=issuer.jwks_url, json=issuer.jwks())
    id_token = issuer.sign({"aud": "client", "sub": "user-1", "nonce": nonce})

``sign`` fills ``iss``, ``iat`` and ``exp``; pass ``None`` for a claim to drop it.
"""

from __future__ import annotations

import json
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm


class OidcTestIssuer:
    """A fake IdP whose endpoints live under ``issuer`` and whose tokens verify."""

    def __init__(self, issuer: str = "https://idp.test/realms/test", kid: str = "test-key") -> None:
        self.issuer = issuer.rstrip("/")
        self.kid = kid
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    @property
    def discovery_url(self) -> str:
        return f"{self.issuer}/.well-known/openid-configuration"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/keys"

    @property
    def authorization_endpoint(self) -> str:
        return f"{self.issuer}/authorize"

    @property
    def token_endpoint(self) -> str:
        return f"{self.issuer}/token"

    def discovery(self) -> dict[str, Any]:
        """The discovery document for this issuer."""
        return {
            "issuer": self.issuer,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "jwks_uri": self.jwks_url,
            "response_types_supported": ["code"],
            "code_challenge_methods_supported": ["S256"],
            "id_token_signing_alg_values_supported": ["RS256"],
        }

    def jwks(self) -> dict[str, Any]:
        """The public signing key as a JWKS document."""
        jwk = json.loads(RSAAlgorithm.to_jwk(self._key.public_key()))
        return {"keys": [{**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def sign(self, claims: dict[str, Any], *, lifetime: int = 300) -> str:
        """An RS256 ID token from this issuer; ``None`` values drop a claim."""
        now = int(time.time())
        payload = {"iss": self.issuer, "iat": now, "exp": now + lifetime, **claims}
        payload = {k: v for k, v in payload.items() if v is not None}
        return jwt.encode(payload, self._key, algorithm="RS256", headers={"kid": self.kid})


@pytest.fixture
def oidc_test_issuer() -> OidcTestIssuer:
    """A fresh :class:`OidcTestIssuer` per test."""
    return OidcTestIssuer()
