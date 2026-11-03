"""Reject ambiguous token purpose and incomplete authenticated claims."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from oidc.jwks import JWKSCache


@pytest.fixture
def signed():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cache = JWKSCache("https://idp/keys", issuer="https://idp", audience="app")
    cache._keys = {"key": key.public_key()}
    cache._fetched_at = time.monotonic()
    payload = {
        "iss": "https://idp",
        "sub": "user",
        "aud": "app",
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
    }

    def sign(changes=None, missing=None):
        claims = {**payload, **(changes or {})}
        if missing:
            claims.pop(missing)
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "key"})

    return cache, sign


@pytest.mark.parametrize("claim", ["iss", "sub", "aud", "exp", "iat"])
async def test_required_claim(signed, claim):
    cache, sign = signed
    assert await cache.validate_jwt(sign(missing=claim)) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"sub": ""},
        {"sub": 3},
        {"exp": True},
        {"exp": "2000000000"},
        {"exp": 1e100},
        {"exp": float("inf")},
        {"iat": float("inf")},
        {"iat": "100"},
        {"iat": True},
        {"iat": 1e100},
        {"aud": ["app", "untrusted"]},
        {"aud": ["app", "api"], "azp": "other"},
        {"aud": ["app", "api"]},
        {"azp": "other"},
    ],
)
async def test_rejects_invalid_claims(signed, changes):
    cache, sign = signed
    assert await cache.validate_jwt(sign(changes)) is None


async def test_audience_is_per_call(signed):
    cache, sign = signed
    assert await cache.validate_jwt(sign(), audience="api") is None
    assert await cache.validate_jwt(sign({"aud": "api"}), audience="api") is not None


async def test_api_token_azp_is_the_calling_client(signed):
    cache, sign = signed
    token = sign({"aud": "api", "azp": "some-spa"})
    assert await cache.validate_jwt(token, audience="api") is not None


async def test_wrong_signature_rejected(signed):
    cache, _ = signed
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(
        {
            "iss": "https://idp",
            "sub": "u",
            "aud": "app",
            "exp": int(time.time()) + 300,
            "iat": int(time.time()),
        },
        other_key,
        algorithm="RS256",
        headers={"kid": "key"},
    )
    assert await cache.validate_jwt(token) is None


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"])
async def test_malformed_tokens_rejected(signed, token):
    cache, _ = signed
    assert await cache.validate_jwt(token) is None


@pytest.mark.parametrize(
    "algorithm,key", [("HS256", "attacker-secret-that-is-over-32-bytes"), ("none", None)]
)
async def test_algorithm_allowlist(signed, algorithm, key):
    cache, _ = signed
    token = jwt.encode(
        {
            "iss": "https://idp",
            "sub": "user",
            "aud": "app",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        },
        key,
        algorithm=algorithm,
        headers={"kid": "key"},
    )
    assert await cache.validate_jwt(token) is None


async def test_small_clock_skew_is_tolerated(signed):
    cache, sign = signed
    # Issued "in the future" by an IdP clock a few seconds ahead of ours.
    assert await cache.validate_jwt(sign({"iat": int(time.time()) + 5})) is not None
    assert await cache.validate_jwt(sign({"iat": int(time.time()) + 60})) is None
