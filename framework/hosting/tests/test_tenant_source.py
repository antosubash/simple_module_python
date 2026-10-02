"""TenantMiddleware records where the tenant came from and merges ``Vary``."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from simple_module_hosting.middleware import TenantMiddleware, TenantResolution


def _scope(headers=None, user=None, resolver=None):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
        "state": {},
        "app": SimpleNamespace(state=SimpleNamespace(tenant_resolver=resolver)),
    }
    if user is not None:
        scope["state"]["user"] = user
    return scope


async def _receive():  # pragma: no cover
    return {"type": "http.request", "body": b"", "more_body": False}


async def _run(mw_kwargs, scope, vary_header: bytes | None = None):
    sent: list[dict] = []

    async def inner(scope, receive, send):
        start = {"type": "http.response.start", "status": 200, "headers": []}
        if vary_header is not None:
            start["headers"].append((b"vary", vary_header))
        await send(start)

    async def send(message):
        sent.append(message)

    await TenantMiddleware(inner, **mw_kwargs)(scope, _receive, send)
    headers = [v.decode() for k, v in sent[0]["headers"] if k == b"vary"]
    return scope["state"], headers


async def test_fixed_source():
    state, vary = await _run({"fixed": "main"}, _scope())
    assert (state["tenant_id"], state["tenant_source"]) == ("main", "fixed")
    assert vary == []


async def test_claim_source():
    state, _ = await _run({}, _scope(user=SimpleNamespace(tenant_id="acme")))
    assert state["tenant_source"] == "claim"


async def test_claim_absent_has_no_source():
    state, _ = await _run({}, _scope(user=SimpleNamespace(tenant_id=None)))
    assert state["tenant_source"] is None


async def test_anon_header_source_and_vary():
    scope = _scope(headers=[(b"x-tenant-id", b"acme")])
    state, vary = await _run({"header": "X-Tenant-ID"}, scope)
    assert state["tenant_source"] == "anon_header"
    assert vary == ["X-Tenant-ID"]


async def test_anon_header_consulted_but_invalid_still_varies():
    scope = _scope(headers=[(b"x-tenant-id", b"x" * 80)])
    state, vary = await _run({"header": "X-Tenant-ID"}, scope)
    assert (state["tenant_id"], state["tenant_source"]) == (None, None)
    assert vary == ["X-Tenant-ID"]


async def test_no_source_no_vary():
    state, vary = await _run({}, _scope())
    assert state["tenant_source"] is None
    assert vary == []


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("acme", ("acme", "resolver")),
        (None, (None, None)),
        (("acme", "session"), ("acme", "session")),
        (TenantResolution("acme", "subdomain"), ("acme", "subdomain")),
    ],
)
async def test_resolver_return_shapes(answer, expected):
    async def resolver(request):
        return answer

    state, _ = await _run({}, _scope(resolver=resolver))
    assert (state["tenant_id"], state["tenant_source"]) == expected


async def test_resolver_vary_is_merged_not_clobbered():
    async def resolver(request):
        return TenantResolution("acme", "header", ("Host", "X-Tenant-ID"))

    _, vary = await _run({}, _scope(resolver=resolver), vary_header=b"Accept-Encoding, host")
    assert vary == ["Accept-Encoding, host, X-Tenant-ID"]  # Host already present


async def test_vary_star_is_left_alone():
    async def resolver(request):
        return TenantResolution("acme", "header", ("X-Tenant-ID",))

    _, vary = await _run({}, _scope(resolver=resolver), vary_header=b"*")
    assert vary == ["*"]
