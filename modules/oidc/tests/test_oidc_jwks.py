"""Tests for JWKS key cache and JWT validation."""

from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from oidc.jwks import JWKSCache


def _generate_rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


def _make_jwks_response(public_key, kid="test-key-1", *, include_alg=True):
    from jwt.algorithms import RSAAlgorithm

    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk["kid"] = kid
    jwk["use"] = "sig"
    if include_alg:
        jwk["alg"] = "RS256"
    return {"keys": [jwk]}


def _sign_token(private_key, payload, kid="test-key-1"):
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def rsa_keys():
    return _generate_rsa_keypair()


@pytest.fixture
def valid_payload():
    now = int(time.time())
    return {
        "oid": "user-123",
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
    httpx_mock.add_response(url="https://idp/jwks", json=_make_jwks_response(public_key))

    cache = JWKSCache(
        jwks_url="https://idp/jwks",
        ttl_seconds=3600,
        issuer="https://login.microsoftonline.com/tid/v2.0",
        audience="my-client",
    )

    token = _sign_token(private_key, valid_payload)
    claims = await cache.validate_jwt(token)
    assert claims is not None
    assert claims["oid"] == "user-123"


async def test_validate_jwt_accepts_keys_without_alg(rsa_keys, valid_payload, httpx_mock):
    """Entra JWKS keys omit ``alg`` — they must still be accepted."""
    private_key, public_key = rsa_keys
    httpx_mock.add_response(
        url="https://idp/jwks",
        json=_make_jwks_response(public_key, include_alg=False),
    )

    cache = JWKSCache(
        jwks_url="https://idp/jwks",
        ttl_seconds=3600,
        issuer="https://login.microsoftonline.com/tid/v2.0",
        audience="my-client",
    )

    token = _sign_token(private_key, valid_payload)
    claims = await cache.validate_jwt(token)
    assert claims is not None
    assert claims["oid"] == "user-123"


async def test_validate_jwt_expired_token(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    valid_payload["exp"] = int(time.time()) - 100
    httpx_mock.add_response(url="https://idp/jwks", json=_make_jwks_response(public_key))

    cache = JWKSCache(
        jwks_url="https://idp/jwks",
        ttl_seconds=3600,
        issuer="https://login.microsoftonline.com/tid/v2.0",
        audience="my-client",
    )

    token = _sign_token(private_key, valid_payload)
    assert await cache.validate_jwt(token) is None


async def test_validate_jwt_wrong_issuer(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    httpx_mock.add_response(url="https://idp/jwks", json=_make_jwks_response(public_key))

    cache = JWKSCache(
        jwks_url="https://idp/jwks",
        ttl_seconds=3600,
        issuer="https://wrong-issuer.example.com/v2.0",
        audience="my-client",
    )

    token = _sign_token(private_key, valid_payload)
    assert await cache.validate_jwt(token) is None


async def test_validate_jwt_wrong_audience(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    httpx_mock.add_response(url="https://idp/jwks", json=_make_jwks_response(public_key))

    cache = JWKSCache(
        jwks_url="https://idp/jwks",
        ttl_seconds=3600,
        issuer="https://login.microsoftonline.com/tid/v2.0",
        audience="wrong-client",
    )

    token = _sign_token(private_key, valid_payload)
    assert await cache.validate_jwt(token) is None


def test_jwks_requires_issuer_and_audience():
    with pytest.raises(ValueError, match="issuer"):
        JWKSCache(jwks_url="https://idp/jwks", issuer="", audience="my-client")
    with pytest.raises(ValueError, match="audience"):
        JWKSCache(jwks_url="https://idp/jwks", issuer="https://idp", audience="")
