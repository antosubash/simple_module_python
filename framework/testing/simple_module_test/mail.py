"""Mail fixtures: capture what the app sends, and never leak a sender between tests.

The process mail sender (``simple_module_core.mail``) is module-level state that
an app's ``mail`` module installs on startup, so a test that boots an app would
otherwise hand its SMTP sender to the next test in the same worker.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from simple_module_core.mail import MailMessage, install_mail_sender


class CapturedMail:
    """A sender that records every message instead of sending it."""

    def __init__(self, *, delivers_email: bool = True) -> None:
        self.delivers_email = delivers_email
        self.messages: list[MailMessage] = []

    async def send(self, message: MailMessage) -> None:
        self.messages.append(message)

    def to(self, address: str) -> list[MailMessage]:
        return [m for m in self.messages if m.to == address]


@pytest.fixture
def captured_mail() -> Iterator[CapturedMail]:
    """Install a recording sender that claims to deliver; yields it.

    Installed after any app fixture requested before it has started, so it wins
    over the ``mail`` module's sender. A ``settings_reloaded`` in the test
    reinstalls the real one; reinstall with ``install_mail_sender(captured)``.
    """
    captured = CapturedMail()
    install_mail_sender(captured)
    yield captured
