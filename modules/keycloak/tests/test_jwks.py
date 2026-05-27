"""Tests for JWKS key cache and JWT validation."""

from __future__ import annotations

import json
import time

import httpx
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


async def test_jwks_cache_refetches_on_unknown_kid(rsa_keys, valid_payload):
    """When a token has a kid not in cache, refetch JWKS once before rejecting."""
    from unittest.mock import AsyncMock, patch

    private_key, public_key = rsa_keys
    jwks_data = _make_jwks_response(public_key, kid="rotated-key")

    call_count = 0
    resp_cls = type("R", (), {"raise_for_status": lambda s: None})

    async def mock_get(self, url, **kw):
        nonlocal call_count
        call_count += 1
        r = resp_cls()
        r.json = lambda: {"keys": []} if call_count == 1 else jwks_data
        return r

    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        ttl_seconds=3600,
        issuer="https://auth.example.com/realms/test",
        audience="my-client",
    )

    token = _sign_token(private_key, valid_payload, kid="rotated-key")
    with patch("httpx.AsyncClient.get", mock_get):
        claims = await cache.validate_jwt(token)
    assert claims is not None
    assert claims["sub"] == "user-123"
    assert call_count == 2
