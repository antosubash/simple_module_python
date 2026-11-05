"""Tests for JWKS key cache and JWT validation."""

from __future__ import annotations

import time

import pytest
from oidc.identity.jwks import JWKSCache
from oidc_flow_helpers import make_jwks_response, sign_token


@pytest.fixture
def valid_payload():
    now = int(time.time())
    return {
        "oid": "user-123",
        "sub": "pairwise-123",
        "email": "test@example.com",
        "preferred_username": "testuser",
        "iss": "https://login.microsoftonline.com/tid/v2.0",
        "aud": "my-client",
        "exp": now + 3600,
        "iat": now,
        "roles": ["admin", "user"],
    }


async def test_validate_jwt_valid_token(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    httpx_mock.add_response(url="https://idp/jwks", json=make_jwks_response(public_key))

    cache = JWKSCache(
        jwks_url="https://idp/jwks",
        ttl_seconds=3600,
        issuer="https://login.microsoftonline.com/tid/v2.0",
        audience="my-client",
    )

    token = sign_token(private_key, valid_payload)
    claims = await cache.validate_jwt(token)
    assert claims is not None
    assert claims["oid"] == "user-123"


async def test_validate_jwt_accepts_keys_without_alg(rsa_keys, valid_payload, httpx_mock):
    """Entra JWKS keys omit ``alg`` — they must still be accepted."""
    private_key, public_key = rsa_keys
    httpx_mock.add_response(
        url="https://idp/jwks",
        json=make_jwks_response(public_key, include_alg=False),
    )

    cache = JWKSCache(
        jwks_url="https://idp/jwks",
        ttl_seconds=3600,
        issuer="https://login.microsoftonline.com/tid/v2.0",
        audience="my-client",
    )

    token = sign_token(private_key, valid_payload)
    claims = await cache.validate_jwt(token)
    assert claims is not None
    assert claims["oid"] == "user-123"


async def test_validate_jwt_expired_token(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    valid_payload["exp"] = int(time.time()) - 100
    httpx_mock.add_response(url="https://idp/jwks", json=make_jwks_response(public_key))

    cache = JWKSCache(
        jwks_url="https://idp/jwks",
        ttl_seconds=3600,
        issuer="https://login.microsoftonline.com/tid/v2.0",
        audience="my-client",
    )

    token = sign_token(private_key, valid_payload)
    assert await cache.validate_jwt(token) is None


async def test_validate_jwt_wrong_issuer(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    httpx_mock.add_response(url="https://idp/jwks", json=make_jwks_response(public_key))

    cache = JWKSCache(
        jwks_url="https://idp/jwks",
        ttl_seconds=3600,
        issuer="https://wrong-issuer.example.com/v2.0",
        audience="my-client",
    )

    token = sign_token(private_key, valid_payload)
    assert await cache.validate_jwt(token) is None


async def test_validate_jwt_wrong_audience(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    httpx_mock.add_response(url="https://idp/jwks", json=make_jwks_response(public_key))

    cache = JWKSCache(
        jwks_url="https://idp/jwks",
        ttl_seconds=3600,
        issuer="https://login.microsoftonline.com/tid/v2.0",
        audience="wrong-client",
    )

    token = sign_token(private_key, valid_payload)
    assert await cache.validate_jwt(token) is None


def test_jwks_requires_issuer_and_audience():
    with pytest.raises(ValueError, match="issuer"):
        JWKSCache(jwks_url="https://idp/jwks", issuer="", audience="my-client")
    with pytest.raises(ValueError, match="audience"):
        JWKSCache(jwks_url="https://idp/jwks", issuer="https://idp", audience="")
