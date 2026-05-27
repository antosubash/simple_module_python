"""Tests for JWKS key cache and JWT validation."""

from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from keycloak.jwks import JWKSCache


def _generate_rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


def _make_jwks_response(public_key, kid="test-key-1"):
    from jwt.algorithms import RSAAlgorithm

    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk["kid"] = kid
    jwk["use"] = "sig"
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
        "sub": "user-123",
        "email": "test@example.com",
        "preferred_username": "testuser",
        "iss": "https://auth.example.com/realms/test",
        "aud": "my-client",
        "exp": now + 3600,
        "iat": now,
        "realm_access": {"roles": ["admin", "user"]},
    }


async def test_validate_jwt_valid_token(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    jwks_data = _make_jwks_response(public_key)
    httpx_mock.add_response(url="https://auth.example.com/jwks", json=jwks_data)

    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        ttl_seconds=3600,
        issuer="https://auth.example.com/realms/test",
        audience="my-client",
    )

    token = _sign_token(private_key, valid_payload)
    claims = await cache.validate_jwt(token)
    assert claims is not None
    assert claims["sub"] == "user-123"
    assert claims["email"] == "test@example.com"


async def test_validate_jwt_expired_token(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    valid_payload["exp"] = int(time.time()) - 100
    jwks_data = _make_jwks_response(public_key)
    httpx_mock.add_response(url="https://auth.example.com/jwks", json=jwks_data)

    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        ttl_seconds=3600,
        issuer="https://auth.example.com/realms/test",
        audience="my-client",
    )

    token = _sign_token(private_key, valid_payload)
    claims = await cache.validate_jwt(token)
    assert claims is None


async def test_validate_jwt_wrong_issuer(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    jwks_data = _make_jwks_response(public_key)
    httpx_mock.add_response(url="https://auth.example.com/jwks", json=jwks_data)

    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        ttl_seconds=3600,
        issuer="https://wrong-issuer.com/realms/test",
        audience="my-client",
    )

    token = _sign_token(private_key, valid_payload)
    claims = await cache.validate_jwt(token)
    assert claims is None


async def test_validate_jwt_wrong_audience(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    jwks_data = _make_jwks_response(public_key)
    httpx_mock.add_response(url="https://auth.example.com/jwks", json=jwks_data)

    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        ttl_seconds=3600,
        issuer="https://auth.example.com/realms/test",
        audience="wrong-client",
    )

    token = _sign_token(private_key, valid_payload)
    claims = await cache.validate_jwt(token)
    assert claims is None


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
async def test_jwks_cache_refetches_on_unknown_kid(rsa_keys, valid_payload, httpx_mock):
    private_key, public_key = rsa_keys
    jwks_data = _make_jwks_response(public_key, kid="rotated-key")
    httpx_mock.add_response(url="https://auth.example.com/jwks", json={"keys": []})
    httpx_mock.add_response(url="https://auth.example.com/jwks", json=jwks_data)

    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        ttl_seconds=3600,
        issuer="https://auth.example.com/realms/test",
        audience="my-client",
    )

    token = _sign_token(private_key, valid_payload, kid="rotated-key")
    claims = await cache.validate_jwt(token)
    assert claims is not None
    assert claims["sub"] == "user-123"
