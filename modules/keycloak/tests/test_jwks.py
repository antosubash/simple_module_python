"""Tests for JWKS key cache and JWT validation."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

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


async def test_jwks_cache_refetches_on_unknown_kid(
    rsa_keys, valid_payload, httpx_mock, monkeypatch
):
    """Rotation is discovered after the short refetch cooldown, before the TTL."""
    private_key, public_key = rsa_keys
    now = 10_000.0
    monkeypatch.setattr("keycloak.jwks.time", SimpleNamespace(monotonic=lambda: now))
    httpx_mock.add_response(json=_make_jwks_response(public_key))
    httpx_mock.add_response(json=_make_jwks_response(public_key, kid="rotated-key"))
    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        issuer="https://auth.example.com/realms/test",
        audience="my-client",
    )
    assert await cache.validate_jwt(_sign_token(private_key, valid_payload)) is not None

    now += 31
    token = _sign_token(private_key, valid_payload, kid="rotated-key")
    claims = await cache.validate_jwt(token)
    assert claims is not None
    assert claims["sub"] == "user-123"
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.parametrize("outage", [False, True])
@pytest.mark.parametrize("ttl", [0, 3600])
async def test_jwks_random_kids_throttle_fetch_attempts(
    rsa_keys, valid_payload, httpx_mock, monkeypatch, outage, ttl
):
    """Random kids cannot bypass the cooldown, even with stale keys or an outage."""
    private_key, public_key = rsa_keys
    now = 10_000.0
    monkeypatch.setattr("keycloak.jwks.time", SimpleNamespace(monotonic=lambda: now))
    if outage:
        httpx_mock.add_exception(httpx.ConnectError("IdP unavailable"), is_reusable=True)
    else:
        httpx_mock.add_response(json=_make_jwks_response(public_key), is_reusable=True)
    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        ttl_seconds=ttl,
        issuer="https://auth.example.com/realms/test",
        audience="my-client",
    )

    for index in range(5):
        now += 1
        token = _sign_token(private_key, valid_payload, kid=f"unknown-{index}")
        assert await cache.validate_jwt(token) is None
    assert len(httpx_mock.get_requests()) == 1

    now += 31
    assert await cache.validate_jwt(token) is None
    assert len(httpx_mock.get_requests()) == 2
    if not outage:
        assert await cache.validate_jwt(_sign_token(private_key, valid_payload)) is not None


@pytest.mark.parametrize("outage", [False, True])
async def test_jwks_concurrent_unknown_kids_share_fetch(
    rsa_keys, valid_payload, httpx_mock, outage
):
    """Overlapping validations perform one fetch, including when that fetch fails."""
    private_key, public_key = rsa_keys
    started = asyncio.Event()
    release = asyncio.Event()

    async def respond(request):
        started.set()
        await release.wait()
        if outage:
            raise httpx.ConnectError("IdP unavailable")
        return httpx.Response(200, json=_make_jwks_response(public_key))

    httpx_mock.add_callback(respond, is_reusable=True)
    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        issuer="https://auth.example.com/realms/test",
        audience="my-client",
    )
    tokens = [_sign_token(private_key, valid_payload, kid=f"unknown-{i}") for i in range(5)]
    tasks = [asyncio.create_task(cache.validate_jwt(token)) for token in tokens]
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        # Let the remaining validations reach the in-flight fetch.
        await asyncio.sleep(0)
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
    assert results == [None] * 5
    assert len(httpx_mock.get_requests()) == 1
