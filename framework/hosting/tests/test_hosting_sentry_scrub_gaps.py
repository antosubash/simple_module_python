"""Scrubber gaps found by an adversarial audit (#538 follow-up).

Each secret below got past the first scrubber; the SDK-driven tests assert it
is absent from the envelope the fake transport receives.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from typing import Any

import pytest
from simple_module_hosting import sentry as sm_sentry
from simple_module_hosting.sentry_scrub import REDACTED, is_sensitive_key, scrub, scrub_event
from simple_module_hosting.sentry_scrub_text import MAX_TEXT, TRUNCATED, scrub_text

sentry_sdk = pytest.importorskip("sentry_sdk")
from _sentry_transport import FakeTransport, start  # noqa: E402

_HEX_KEY = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJlLWp3dA"


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeTransport]:
    fake = start(monkeypatch, sm_sentry.PROCESS_WEB)
    yield fake
    sentry_sdk.get_global_scope().client.close()


def _capture(message: str) -> None:
    try:
        raise RuntimeError(message)
    except RuntimeError:
        sentry_sdk.capture_exception()
    sentry_sdk.flush()


def test_tags_contexts_pairs_and_free_text_are_scrubbed(web: FakeTransport) -> None:
    sentry_sdk.set_tag("auth_token", "tag-s3cret")
    sentry_sdk.set_user({"email": "who@example.com", "username": "who"})
    sentry_sdk.set_context(
        "svc",
        {
            "basicAuth": "camel-s3cret",
            "pwd": "pwd-s3cret",
            "headers": [["X-Auth-Token", "pair-s3cret"], ("Set-Cookie", "sc-s3cret")],
            "raw": b"session=bytes-s3cret",
            "region": "eu",
        },
    )
    _capture(
        f"redis://:p@ss/w0rd@cache:6379 jwt {_JWT} key {_HEX_KEY} "
        '{"password": "two words"} {\\"secret\\": \\"esc-s3cret\\"}'
        "\nCookie: sid=a; other=ck-s3cret"
    )
    (event,) = web.of("event")
    dumped = json.dumps(event)
    for secret in (
        "tag-s3cret",
        "who@example.com",
        "camel-s3cret",
        "pwd-s3cret",
        "pair-s3cret",
        "sc-s3cret",
        "bytes-s3cret",
        "p@ss/w0rd",
        "w0rd",
        _JWT,
        _HEX_KEY,
        "two words",
        "words",
        "esc-s3cret",
        "ck-s3cret",
    ):
        assert secret not in dumped, secret
    assert "user" not in event  # no id, so nothing about the user at all
    assert event["contexts"]["svc"]["region"] == "eu"
    assert "cache:6379" in dumped


def test_sentry_ids_survive_the_long_token_rule(web: FakeTransport) -> None:
    _capture("boom")
    (event,) = web.of("event")
    trace = event["contexts"]["trace"]
    assert len(event["event_id"]) == 32 and REDACTED not in event["event_id"]
    assert REDACTED not in trace["trace_id"] and REDACTED not in trace["span_id"]


def test_scrubber_failure_drops_the_event(
    web: FakeTransport, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def explode(event: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("password=fail-s3cret")

    monkeypatch.setattr(sm_sentry, "scrub_event", explode)
    caplog.set_level(logging.WARNING)
    _capture("token=raw-s3cret")
    assert web.of("event") == []
    assert "fail-s3cret" not in caplog.text and "raw-s3cret" not in caplog.text
    assert "ValueError" in caplog.text


def test_unlisted_fields_and_top_level_stacktrace_are_scrubbed() -> None:
    event: dict[str, Any] = {
        "stacktrace": {
            "frames": [{"context_line": 'api_key = "src-s3cret"', "vars": {"x": "var-s3cret"}}]
        },
        "threads": {"values": [{"stacktrace": {"frames": [{"vars": {"y": "thr-s3cret"}}]}}]},
        "request": {"headers": [["Authorization", "hdr-s3cret"], ["Accept", "json"]]},
        "spans": [{"data": {"db.params": ["sql-s3cret"], "db.system": "postgresql"}}],
        "server_name": "web-1 token=srv-s3cret",
        "logentry": {"message": "%s", "params": [b"secret=b-s3cret"]},
        "user": {"id": "u-1", "email": "e@x", "ip_address": "198.51.100.4"},
        "future_sdk_field": {"refreshToken": "new-s3cret"},
    }
    scrubbed = scrub_event(event)
    dumped = json.dumps(scrubbed)
    for secret in ("s3cret", "198.51.100.4", "e@x"):
        assert secret not in dumped, secret
    assert scrubbed["request"]["headers"] == [["Accept", "json"]]
    assert scrubbed["user"] == {"id": "u-1"}
    assert scrubbed["spans"][0]["data"] == {"db.system": "postgresql"}


@pytest.mark.parametrize(
    "key",
    [
        *("pwd", "passwd", "Passphrase", "access_token", "refresh_token", "client_secret"),
        *("private_key", "x-api-key", "apiKey", "authToken", "basicAuth", "authHeader"),
        *("X-Amz-Signature", "sig", "jwt", "otp", "userPin", "DB_PASS", "AUTH"),
    ],
)
def test_sensitive_key_variants(key: str) -> None:
    assert is_sensitive_key(key)


@pytest.mark.parametrize("key", ["author", "authority", "spinner", "bypass", "side", "region"])
def test_bounded_words_do_not_overmatch(key: str) -> None:
    assert not is_sensitive_key(key)


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ("https://user:p@ss@host/x", "ss"),
        ("postgresql://u:a/b@db/x", "a/b"),
        ("Authorization: Digest username=bob, response=dg-1", "dg-1"),
        ("set-cookie: a=1; Path=/; csrftoken=ck-2", "ck-2"),
        ("password='with spaces here'", "spaces"),
        (f"Bearer-less {_JWT} trailing", _JWT),
        ("token " + "Ab3dE" * 8, "Ab3dE" * 8),
    ],
)
def test_scrub_text_gaps(raw: str, secret: str) -> None:
    assert secret not in scrub_text(raw)


@pytest.mark.parametrize(
    "keep",
    [
        "3f2b9c1d-8e7a-4b5c-9d2e-1f0a9b8c7d6e",
        "test_hosting_sentry_scrub_redacts_inline_credentials2",
        "/home/app/simple_module_hosting/sentry_scrub.py",
        "http://host:8080/orders?page=2",
    ],
)
def test_scrub_text_keeps_debugging_signal(keep: str) -> None:
    assert scrub_text(keep) == keep


def test_scrub_is_idempotent() -> None:
    once = scrub_text("Cookie: a=b; c=d url=http://h/x?session=s1")
    assert scrub_text(once) == once


def test_scrub_text_is_linear_on_adversarial_input() -> None:
    payloads = [
        "a" * 1_000_000,
        "password" + " " * 1_000_000,
        "a://" * 250_000,
        "x" * 500_000 + "=" * 3 + "x" * 500_000,
        '"secret": "' + "a" * 1_000_000,
        "token_" * 200_000,
    ]
    started = time.monotonic()
    for payload in payloads:
        assert len(scrub_text(payload)) <= MAX_TEXT + len(TRUNCATED)
    assert time.monotonic() - started < 10  # the quadratic version took minutes
    # Below the cap the patterns themselves must stay fast.
    started = time.monotonic()
    for payload in payloads:
        scrub_text(payload[: MAX_TEXT - 1])
    assert time.monotonic() - started < 10


def test_cyclic_and_deep_structures_end_redacted() -> None:
    cyclic: dict[str, Any] = {"name": "x"}
    cyclic["self"] = cyclic
    deep: list[Any] = []
    node = deep
    for _ in range(1000):
        child: list[Any] = []
        node.append(child)
        node = child
    assert REDACTED in json.dumps(scrub(cyclic))
    assert REDACTED in json.dumps(scrub(deep))
