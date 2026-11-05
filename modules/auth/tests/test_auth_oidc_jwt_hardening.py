"""Both providers enforce the shared JWT policy (#741)."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from keycloak.identity.jwks import JWKSCache as KeycloakJWKS
from oidc.identity.jwks import JWKSCache as OidcJWKS


@pytest.fixture(params=[KeycloakJWKS, OidcJWKS])
def signed(request):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cache = request.param("https://idp/keys", issuer="https://idp", audience="app")
    cache._keys = {"key": key.public_key()}
    cache._fetched_at = time.monotonic()

    def sign(changes=None, missing=None):
        claims = {
            "iss": "https://idp",
            "sub": "user",
            "aud": "app",
            "exp": int(time.time()) + 300,
            "iat": int(time.time()),
        }
        claims.update(changes or {})
        if missing:
            claims.pop(missing)
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "key"})

    return cache, sign


@pytest.mark.parametrize("claim", ["iss", "sub", "aud", "exp", "iat"])
async def test_required_claims(signed, claim):
    cache, sign = signed
    assert await cache.validate_jwt(sign(missing=claim)) is None


async def test_clock_leeway(signed):
    cache, sign = signed
    assert await cache.validate_jwt(sign({"iat": int(time.time()) + 5})) is not None
    assert await cache.validate_jwt(sign({"iat": int(time.time()) + 60})) is None


async def test_rejects_other_authorized_party(signed):
    cache, sign = signed
    assert await cache.validate_jwt(sign({"azp": "other"})) is None
