"""OIDC key rotation and bounded single-flight fetches."""

import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest
from oidc.identity.jwks import JWKSCache
from oidc_flow_helpers import make_jwks_response, sign_token


@pytest.fixture
def valid_payload():
    return {
        "sub": "user-123",
        "iss": "https://auth.example.com/realms/test",
        "aud": "my-client",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }


async def test_jwks_cache_refetches_on_unknown_kid(
    rsa_keys, valid_payload, httpx_mock, monkeypatch
):
    """Rotation is discovered after the short refetch cooldown, before the TTL."""
    private_key, public_key = rsa_keys
    now = 10_000.0
    monkeypatch.setattr("auth.oidc_common.jwks.time", SimpleNamespace(monotonic=lambda: now))
    httpx_mock.add_response(json=make_jwks_response(public_key))
    httpx_mock.add_response(json=make_jwks_response(public_key, kid="rotated-key"))
    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        issuer="https://auth.example.com/realms/test",
        audience="my-client",
    )
    assert await cache.validate_jwt(sign_token(private_key, valid_payload)) is not None

    now += 31
    token = sign_token(private_key, valid_payload, kid="rotated-key")
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
    monkeypatch.setattr("auth.oidc_common.jwks.time", SimpleNamespace(monotonic=lambda: now))
    if outage:
        httpx_mock.add_exception(httpx.ConnectError("IdP unavailable"), is_reusable=True)
    else:
        httpx_mock.add_response(json=make_jwks_response(public_key), is_reusable=True)
    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        ttl_seconds=ttl,
        issuer="https://auth.example.com/realms/test",
        audience="my-client",
    )

    for index in range(5):
        now += 1
        token = sign_token(private_key, valid_payload, kid=f"unknown-{index}")
        assert await cache.validate_jwt(token) is None
    assert len(httpx_mock.get_requests()) == 1

    now += 31
    assert await cache.validate_jwt(token) is None
    assert len(httpx_mock.get_requests()) == 2
    if not outage:
        assert await cache.validate_jwt(sign_token(private_key, valid_payload)) is not None


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
        return httpx.Response(200, json=make_jwks_response(public_key))

    httpx_mock.add_callback(respond, is_reusable=True)
    cache = JWKSCache(
        jwks_url="https://auth.example.com/jwks",
        issuer="https://auth.example.com/realms/test",
        audience="my-client",
    )
    tokens = [sign_token(private_key, valid_payload, kid=f"unknown-{i}") for i in range(5)]
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


@pytest.mark.parametrize("bad", [[], {"keys": 3}, {"keys": [None, "invalid"]}, {"keys": []}])
async def test_last_good_keys_survive_malformed_metadata(
    rsa_keys, valid_payload, httpx_mock, monkeypatch, bad
):
    private, public = rsa_keys
    now = 10000
    monkeypatch.setattr("auth.oidc_common.jwks.time", SimpleNamespace(monotonic=lambda: now))
    httpx_mock.add_response(json=make_jwks_response(public))
    httpx_mock.add_response(json=bad)
    cache = JWKSCache(
        "https://idp/keys", ttl_seconds=0, issuer=valid_payload["iss"], audience="my-client"
    )
    token = sign_token(private, valid_payload)
    assert await cache.validate_jwt(token)
    now += 31
    assert await cache.validate_jwt(token)
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"kty": "EC"},
        {"alg": "HS256"},
        {"use": "enc"},
        {"kid": []},
        {"key_ops": ["encrypt"]},
        {"issuer": "https://wrong"},
    ],
)
async def test_incompatible_keys_rejected(rsa_keys, valid_payload, httpx_mock, changes):
    private, public = rsa_keys
    doc = make_jwks_response(public)
    doc["keys"][0].update(changes)
    httpx_mock.add_response(json=doc)
    cache = JWKSCache("https://idp/keys", issuer=valid_payload["iss"], audience="my-client")
    assert await cache.validate_jwt(sign_token(private, valid_payload)) is None


async def test_entra_template_key_issuer_is_bound_to_concrete_tenant(rsa_keys, httpx_mock):
    private, public = rsa_keys
    doc = make_jwks_response(public)
    doc["keys"][0]["issuer"] = "https://login.microsoftonline.com/{tenantid}/v2.0"
    httpx_mock.add_response(json=doc)
    cache = JWKSCache(
        "https://idp/keys", issuer="https://login.microsoftonline.com/tenant/v2.0", audience="app"
    )
    claims = {
        "iss": "https://login.microsoftonline.com/tenant/v2.0",
        "sub": "user",
        "aud": "app",
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
    }
    assert await cache.validate_jwt(sign_token(private, claims)) is not None


async def test_last_good_keys_survive_network_failure(
    rsa_keys, valid_payload, httpx_mock, monkeypatch
):
    private, public = rsa_keys
    now = 10000
    monkeypatch.setattr("auth.oidc_common.jwks.time", SimpleNamespace(monotonic=lambda: now))
    httpx_mock.add_response(json=make_jwks_response(public))
    httpx_mock.add_response(status_code=503)
    cache = JWKSCache(
        "https://idp/keys", ttl_seconds=0, issuer=valid_payload["iss"], audience="my-client"
    )
    token = sign_token(private, valid_payload)
    assert await cache.validate_jwt(token)
    now += 31
    assert await cache.validate_jwt(token)
    assert await cache.validate_jwt(token)
    assert len(httpx_mock.get_requests()) == 2
