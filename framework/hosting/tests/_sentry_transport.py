"""A fake Sentry transport: the real SDK pipeline, envelopes kept in memory."""

from __future__ import annotations

from typing import Any

import pytest
from sentry_sdk.transport import Transport
from simple_module_hosting import sentry as sm_sentry

DSN_KEY = "dsnpublickey0123"
DSN = f"https://{DSN_KEY}@o0.ingest.sentry.io/1"


class FakeTransport(Transport):
    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self.payloads: list[dict[str, Any]] = []

    def capture_envelope(self, envelope: Any) -> None:
        for item in envelope.items:
            if item.type in ("event", "transaction"):
                self.payloads.append(item.payload.json)

    def of(self, kind: str) -> list[dict[str, Any]]:
        return [p for p in self.payloads if p.get("type", "event") == kind]


def start(monkeypatch: pytest.MonkeyPatch, process: sm_sentry.Process) -> FakeTransport:
    monkeypatch.setenv("SM_SENTRY_DSN", DSN)
    monkeypatch.setenv("SM_SENTRY_TRACES_SAMPLE_RATE", "1.0")
    fake = FakeTransport()
    assert sm_sentry.init_sentry(process, transport=fake)
    return fake
