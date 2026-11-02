"""Optional Sentry (#538): tagging, scrubbing, and the no-DSN zero-cost path."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request
from simple_module_db.tenancy import current_tenant_id
from simple_module_hosting import sentry as sm_sentry

sentry_sdk = pytest.importorskip("sentry_sdk")
from sentry_sdk.transport import Transport  # noqa: E402

_TENANT = "acme"
_USER_ID = "user-42"
_SECRET_HEADERS = ("authorization", "cookie", "x-csrf-token", "x-api-key")


class FakeTransport(Transport):
    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self.events: list[dict[str, Any]] = []

    def capture_envelope(self, envelope: Any) -> None:
        for item in envelope.items:
            if item.type == "event":
                self.events.append(item.payload.json)


class _User:
    id = _USER_ID
    email = "private@example.com"


def boom(request: Request) -> None:
    # What the tenant/auth/correlation middlewares leave on the scope state.
    request.state.tenant_id = _TENANT
    request.state.user = _User()
    request.state.correlation_id = "cid-1"
    raise RuntimeError("route failure")


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeTransport]:
    monkeypatch.setenv("SM_SENTRY_DSN", "https://key@o0.ingest.sentry.io/1")
    fake = FakeTransport()
    assert sm_sentry.init_sentry(sm_sentry.PROCESS_WEB, transport=fake)
    yield fake
    sentry_sdk.get_global_scope().client.close()


async def test_route_exception_is_tagged_and_scrubbed(transport: FakeTransport) -> None:
    app = FastAPI()
    app.add_middleware(sm_sentry.SentryContextMiddleware)
    app.add_api_route("/boom", boom, methods=["POST"])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        await client.post(
            "/boom?token=s3cret&code=oauthcode9&keep=1",
            headers={
                "Authorization": "Bearer x",
                "Cookie": "sm=1",
                "X-CSRF-Token": "t",
                "X-Api-Key": "k",
            },
            content=b'{"password": "hunter2"}',
        )
    sentry_sdk.flush()
    assert len(transport.events) == 1
    event = transport.events[0]
    assert event["tags"]["tenant"] == _TENANT
    assert event["tags"]["module"] == __name__.split(".")[0]
    assert event["tags"]["request_id"] == "cid-1"
    assert event["user"] == {"id": _USER_ID}
    request = event["request"]
    assert not {h.lower() for h in request.get("headers", {})} & set(_SECRET_HEADERS)
    dumped = str(event)
    for leaked in ("s3cret", "oauthcode9", "hunter2", "Bearer x", "private@example.com"):
        assert leaked not in dumped
    assert "keep=1" in dumped


def test_task_exception_is_tagged(monkeypatch: pytest.MonkeyPatch) -> None:
    from celery import Celery

    monkeypatch.setenv("SM_SENTRY_DSN", "https://key@o0.ingest.sentry.io/1")
    fake = FakeTransport()
    assert sm_sentry.init_sentry(sm_sentry.PROCESS_WORKER, transport=fake)
    celery = Celery("t", broker="memory://", task_always_eager=True)

    @celery.task(name="orders.explode")
    def explode() -> None:
        raise RuntimeError("task failure")

    try:
        token = current_tenant_id.set(_TENANT)
        try:
            with pytest.raises(RuntimeError):
                explode.apply(throw=True).get()
        finally:
            current_tenant_id.reset(token)
        sentry_sdk.flush()
    finally:
        sentry_sdk.get_global_scope().client.close()
    event = next(e for e in fake.events if "exception" in e)
    assert event["tags"]["tenant"] == _TENANT
    assert event["tags"]["module"] == "orders"
    assert event["tags"]["task"] == "orders.explode"


def test_no_dsn_never_imports_sdk() -> None:
    code = textwrap.dedent(
        """
        import os, sys
        os.environ.pop("SM_SENTRY_DSN", None)
        from simple_module_hosting.app_builder import create_app
        from simple_module_hosting.sentry import PROCESS_WEB, init_sentry
        assert init_sentry(PROCESS_WEB) is False
        create_app()
        assert "sentry_sdk" not in sys.modules, "sentry_sdk imported without a DSN"
        """
    )
    env = {k: v for k, v in __import__("os").environ.items() if k != "SM_SENTRY_DSN"}
    env["SM_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=False
    )
    assert result.returncode == 0, result.stderr[-2000:]
