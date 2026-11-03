"""Both providers use single-flight JWKS fetches and retain last-good keys."""

import asyncio
import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from keycloak.jwks import JWKSCache as KeycloakJWKS
from oidc.jwks import JWKSCache as OidcJWKS


@pytest.fixture(params=[KeycloakJWKS, OidcJWKS])
def keys(request, monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cache = request.param("https://idp/keys", issuer="https://idp", audience="app")
    clock = [10_000.0]
    monkeypatch.setattr(cache, "_now", lambda: clock[0])
    jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    jwk.update(kid="key", use="sig")  # alg is optional in JWKS.

    def sign(kid="key"):
        return jwt.encode(
            {
                "iss": "https://idp",
                "sub": "s",
                "aud": "app",
                "exp": int(time.time()) + 300,
                "iat": int(time.time()),
            },
            private,
            algorithm="RS256",
            headers={"kid": kid},
        )

    return cache, clock, jwk, sign


@pytest.mark.parametrize("outage", [False, True])
async def test_concurrent_misses_share_one_fetch_and_cooldown(keys, httpx_mock, outage):
    cache, clock, jwk, sign = keys
    started, release = asyncio.Event(), asyncio.Event()

    async def respond(request):
        started.set()
        await release.wait()
        if outage:
            raise httpx.ConnectError("offline")
        return httpx.Response(200, json={"keys": [jwk]})

    httpx_mock.add_callback(respond)
    tasks = [asyncio.create_task(cache.validate_jwt(sign(f"unknown-{i}"))) for i in range(4)]
    try:
        await asyncio.wait_for(started.wait(), 2)
        await asyncio.sleep(0)
    finally:
        release.set()
    assert await asyncio.wait_for(asyncio.gather(*tasks), 2) == [None] * 4
    clock[0] += 1
    assert await cache.validate_jwt(sign("another")) is None
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.parametrize("replacement", ["network", "malformed", "encryption", "wrong-alg"])
async def test_bad_refresh_keeps_last_good_keys(keys, httpx_mock, replacement):
    cache, clock, jwk, sign = keys
    httpx_mock.add_response(json={"keys": [jwk]})
    assert await cache.validate_jwt(sign()) is not None
    clock[0] += 3601
    if replacement == "network":
        httpx_mock.add_exception(httpx.ConnectError("offline"))
    else:
        payload = (
            {"keys": [{**jwk, "use": "enc"}]}
            if replacement == "encryption"
            else (
                {"keys": [{**jwk, "alg": "HS256"}]}
                if replacement == "wrong-alg"
                else {"keys": None}
            )
        )
        httpx_mock.add_response(json=payload)
    assert await cache.validate_jwt(sign()) is not None
    assert len(httpx_mock.get_requests()) == 2
