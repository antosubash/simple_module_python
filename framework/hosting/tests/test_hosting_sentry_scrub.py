"""Sentry events never carry secrets or client addresses (#538 follow-up).

Each test drives the real SDK through a fake transport and asserts the secret
is absent from the serialized envelope payload.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request
from simple_module_hosting import sentry as sm_sentry
from simple_module_hosting.sentry_scrub import REDACTED, scrub_event, scrub_text

sentry_sdk = pytest.importorskip("sentry_sdk")
from _sentry_transport import DSN_KEY as _DSN_KEY  # noqa: E402
from _sentry_transport import FakeTransport  # noqa: E402
from _sentry_transport import start as _start  # noqa: E402

_LEAKS = (
    "c00kie-val",
    "203.0.113.9",
    "proxy-cred",
    "hdr-t0ken",
    "sess-1d",
    "q-t0ken",
    "exc-passw0rd",
    "bearer-abc",
    "log-s3cret",
    "up-k3y",
    "nested-s3cret",
    "ctx-s3cret",
    "frame-l0cal",
)


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeTransport]:
    fake = _start(monkeypatch, sm_sentry.PROCESS_WEB)
    yield fake
    sentry_sdk.get_global_scope().client.close()


def leak(request: Request) -> None:
    # Built at runtime so only a frame-locals capture (not source context) could leak it.
    frame_local = "frame-" + "l0cal"  # noqa: F841
    logging.getLogger("app.audit").warning("refresh failed token=log-s3cret for user")
    upstream = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    upstream.get("http://up.example/v1?api_key=up-k3y&page=2")
    sentry_sdk.set_extra("job", {"config": {"db_password": "nested-s3cret", "size": 3}})
    sentry_sdk.set_context("oauth", {"refresh_token": "ctx-s3cret", "provider": "github"})
    raise RuntimeError("login rejected password=exc-passw0rd header Bearer bearer-abc")


async def _hit(app: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        await client.get(
            "/leak?access_token=q-t0ken&page=1",
            headers={
                "Cookie": "sm_session=c00kie-val",
                "X-Forwarded-For": "203.0.113.9",
                "X-Real-IP": "203.0.113.9",
                "Proxy-Authorization": "Basic proxy-cred",
                "X-Auth-Token": "hdr-t0ken",
                "X-Session-Id": "sess-1d",
                "X-Request-Id": "keep-me",
            },
        )
    sentry_sdk.flush()


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(sm_sentry.SentryContextMiddleware)
    app.add_api_route("/leak", leak, methods=["GET"])
    return app


async def test_error_event_carries_no_secret(web: FakeTransport) -> None:
    await _hit(_app())
    (event,) = web.of("event")
    dumped = json.dumps(event)
    for secret in _LEAKS:
        assert secret not in dumped, secret
    request = event["request"]
    assert "cookies" not in request
    assert "env" not in request  # REMOTE_ADDR
    headers = {h.lower() for h in request["headers"]}
    assert not headers & {"cookie", "x-forwarded-for", "x-real-ip", "proxy-authorization"}
    assert not headers & {"x-auth-token", "x-session-id"}
    assert request["headers"].get("x-request-id") == "keep-me"
    assert "ip_address" not in event.get("user", {})
    frames = event["exception"]["values"][0]["stacktrace"]["frames"]
    assert all("vars" not in f for f in frames)
    # Non-secret signal survives.
    assert "page=1" in request["query_string"]
    assert "page=2" in dumped
    assert event["extra"]["job"]["config"] == {"db_password": REDACTED, "size": 3}
    assert event["contexts"]["oauth"]["provider"] == "github"


async def test_transaction_event_is_scrubbed_too(web: FakeTransport) -> None:
    await _hit(_app())
    (transaction,) = web.of("transaction")
    dumped = json.dumps(transaction)
    for secret in ("c00kie-val", "203.0.113.9", "hdr-t0ken", "q-t0ken", "up-k3y"):
        assert secret not in dumped, secret
    assert transaction["tags"]["process"] == sm_sentry.PROCESS_WEB


def test_task_args_and_kwargs_are_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    from celery import Celery

    fake = _start(monkeypatch, sm_sentry.PROCESS_WORKER)
    celery = Celery("t", broker="memory://", task_always_eager=True)

    @celery.task(name="orders.charge")
    def charge(card: str, *, api_secret: str) -> None:
        raise RuntimeError("charge failed")

    card, secret = "4111" + "-arg-card", "kw-" + "s3cret"  # runtime-only values
    try:
        with pytest.raises(RuntimeError):
            charge.apply(args=(card,), kwargs={"api_secret": secret}, throw=True)
        sentry_sdk.flush()
    finally:
        sentry_sdk.get_global_scope().client.close()
    events = [e for e in fake.of("event") if "exception" in e]
    assert events
    for event in events:
        dumped = json.dumps(event)
        assert "4111-arg-card" not in dumped
        assert "kw-s3cret" not in dumped
        job = event.get("extra", {}).get("celery-job", {})
        assert "args" not in job and "kwargs" not in job


def test_dsn_is_never_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _start(monkeypatch, sm_sentry.PROCESS_WEB)
    sentry_sdk.get_global_scope().client.close()
    assert _DSN_KEY not in caplog.text


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ("GET /cb?code=x&refresh_token=rt-1&state=s", "rt-1"),
        ('{"client_secret": "cs-1", "id": 4}', "cs-1"),
        ("Authorization: Bearer ab.cd.ef", "ab.cd.ef"),
        ("postgresql://app:pg-pass@db:5432/x", "pg-pass"),
        ("X-API-Key=ak-1", "ak-1"),
        ("csrf-token: cf-1", "cf-1"),
    ],
)
def test_scrub_text_redacts_inline_credentials(raw: str, secret: str) -> None:
    assert secret not in scrub_text(raw)


def test_url_transaction_names_and_paths_lose_ids() -> None:
    event: dict[str, Any] = {
        "transaction": "/invite/accept/3f2b9c1d8e7a6b5c4d3e2f1a0b9c8d7e6f5a",
        "transaction_info": {"source": "url"},
        "request": {"url": "http://h/orders/12345/items?session=s1"},
        "breadcrumbs": {"values": [{"message": "x", "data": {"http.query": "token=bt-1"}}]},
    }
    scrubbed = scrub_event(event)
    assert scrubbed["transaction"] == "/invite/accept/*"
    assert scrubbed["request"]["url"] == f"http://h/orders/*/items?session={REDACTED}"
    assert "bt-1" not in json.dumps(scrubbed["breadcrumbs"])
