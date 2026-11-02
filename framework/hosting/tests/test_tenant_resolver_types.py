"""A tenant resolver's answer is checked at the boundary (#507).

Before, any object a resolver returned flowed into ``request.state.tenant_id``
and on into string comparisons and tenant filters. A UUID is coerced to its
string form; anything else that isn't ``str | None`` is a resolver bug.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from simple_module_hosting._tenant import _normalise
from simple_module_hosting.middleware import TenantMiddleware, TenantResolution

_ID = UUID("12345678-1234-5678-1234-567812345678")


@pytest.mark.parametrize(
    "result",
    [_ID, (_ID, "header"), TenantResolution(_ID, "header")],
    ids=["bare", "pair", "resolution"],
)
def test_uuid_becomes_its_string(result):
    assert _normalise(result).tenant_id == str(_ID)


@pytest.mark.parametrize(
    "result",
    [42, (42, "header"), ("t1", 7), TenantResolution(42, "header"), object()],
    ids=["int", "int-pair", "int-source", "int-resolution", "object"],
)
def test_other_types_are_refused(result):
    with pytest.raises(TypeError, match="tenant resolver returned"):
        _normalise(result)


def test_str_and_none_pass_through_unchanged():
    assert _normalise("t1") == TenantResolution("t1", "resolver")
    assert _normalise(None) == TenantResolution(None, None)
    assert _normalise(("t1", "session")) == TenantResolution("t1", "session")
    assert _normalise(()) == TenantResolution(None, None)
    vary = ("Host",)
    assert _normalise(TenantResolution(None, "header", vary)) == TenantResolution(None, None, vary)


async def test_middleware_refuses_an_int_tenant():
    async def resolver(request):
        return 42

    async def inner(scope, receive, send):  # pragma: no cover - never reached
        raise AssertionError("request must not reach the app")

    async def receive():  # pragma: no cover
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):  # pragma: no cover
        pass

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "state": {},
        "app": SimpleNamespace(state=SimpleNamespace(tenant_resolver=resolver)),
    }
    with pytest.raises(TypeError):
        await TenantMiddleware(inner)(scope, receive, send)
