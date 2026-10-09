"""TenantMiddleware merges every Vary line (#423); no tenant bound means no source (#424)."""

from __future__ import annotations

from types import SimpleNamespace

from simple_module_hosting._tenant import merge_vary
from simple_module_hosting.middleware import TenantMiddleware, TenantResolution


def _scope(resolver=None, user=None):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "state": {},
        "app": SimpleNamespace(state=SimpleNamespace(tenant_resolver=resolver)),
    }
    if user is not None:
        scope["state"]["user"] = user
    return scope


async def _receive():  # pragma: no cover
    return {"type": "http.request", "body": b"", "more_body": False}


async def _run(scope, vary_lines: list[bytes]):
    sent: list[dict] = []

    async def inner(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"vary", v) for v in vary_lines],
            }
        )

    async def send(message):
        sent.append(message)

    await TenantMiddleware(inner)(scope, _receive, send)
    return scope["state"], [v.decode() for k, v in sent[0]["headers"] if k == b"vary"]


def _resolver(result):
    async def resolve(_request):
        return result

    return resolve


async def test_every_vary_line_is_merged_into_one():
    _, vary = await _run(
        _scope(_resolver(TenantResolution("acme", "header", ("Host",)))),
        [b"Accept", b"Accept-Language"],
    )
    assert vary == ["Accept, Accept-Language, Host"]


async def test_a_wildcard_on_any_line_leaves_the_response_untouched():
    _, vary = await _run(
        _scope(_resolver(TenantResolution("acme", "header", ("Host",)))), [b"Accept", b"*"]
    )
    assert vary == ["Accept", "*"]


def test_existing_duplicates_are_collapsed_case_insensitively():
    assert merge_vary("Accept, accept", ("Host",)) == "Accept, Host"


async def test_no_tenant_means_no_source_but_vary_is_kept():
    state, vary = await _run(
        _scope(_resolver(TenantResolution(None, "header", ("X-Tenant-ID",)))), []
    )
    assert state["tenant_id"] is None
    assert state["tenant_source"] is None
    assert vary == ["X-Tenant-ID"]


async def test_resolution_vary_is_recorded_on_request_state():
    state, _ = await _run(_scope(_resolver(TenantResolution("acme", "subdomain", ("Host",)))), [])
    assert state["tenant_vary"] == ("Host",)


async def test_claim_source_varies_on_the_credential_headers():
    state, vary = await _run(_scope(user=SimpleNamespace(tenant_id="acme")), [])
    assert state["tenant_source"] == "claim"
    assert vary == ["Cookie, Authorization"]
