"""Resolution order of the process mail sender (GH #496)."""

from __future__ import annotations

import logging

import pytest
from simple_module_core import mail
from simple_module_core.mail import (
    ConsoleMailSender,
    MailMessage,
    MailSender,
    current_mail_sender,
    install_mail_resolver,
    install_mail_sender,
    resolve_mail_sender,
)


class _Recording:
    delivers_email = True

    def __init__(self) -> None:
        self.sent: list[MailMessage] = []

    async def send(self, message: MailMessage) -> None:
        self.sent.append(message)


@pytest.fixture(autouse=True)
def _clean_state():
    install_mail_sender(None)
    install_mail_resolver(None)
    yield
    install_mail_sender(None)
    install_mail_resolver(None)


def test_nothing_installed_gives_a_console_sender() -> None:
    assert isinstance(current_mail_sender(), ConsoleMailSender)
    assert current_mail_sender().delivers_email is False


async def test_installed_sender_wins_over_the_resolver() -> None:
    sender = _Recording()
    install_mail_sender(sender)

    async def _resolver(db):
        raise AssertionError("resolver must not run while a sender is installed")

    install_mail_resolver(_resolver)
    assert current_mail_sender() is sender
    assert await resolve_mail_sender(object()) is sender


async def test_resolver_is_used_with_a_session_when_no_sender_is_installed() -> None:
    built = _Recording()
    seen = []

    async def _resolver(db):
        seen.append(db)
        return built

    install_mail_resolver(_resolver)
    session = object()
    assert await resolve_mail_sender(session) is built
    assert seen == [session]
    # Without a session there is nothing to build from.
    assert isinstance(await resolve_mail_sender(), ConsoleMailSender)
    # The sync accessor never runs the resolver.
    assert isinstance(current_mail_sender(), ConsoleMailSender)


async def test_console_sender_logs_instead_of_sending(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="simple_module.mail"):
        await ConsoleMailSender().send(MailMessage("a@example.com", "Hi", "Body text"))
    assert "a@example.com" in caplog.text
    assert "Body text" in caplog.text


def test_protocol_is_runtime_checkable() -> None:
    assert isinstance(_Recording(), MailSender)
    assert isinstance(ConsoleMailSender(), MailSender)
    assert mail.MailSender is MailSender


async def test_fallback_sender_never_logs_the_body(caplog) -> None:
    """Bodies carry one-time tokens; an unconfigured install must not log them."""
    with caplog.at_level(logging.INFO, logger="simple_module.mail"):
        await current_mail_sender().send(MailMessage("a@example.com", "Hi", "token=s3cr3t"))
    assert "a@example.com" in caplog.text
    assert "s3cr3t" not in caplog.text


async def test_transport_installed_tracks_sender_or_resolver() -> None:
    from simple_module_core.mail import mail_transport_installed

    assert mail_transport_installed() is False
    install_mail_sender(_Recording())
    assert mail_transport_installed() is True
    install_mail_sender(None)

    async def _resolver(db):
        return _Recording()

    install_mail_resolver(_resolver)
    assert mail_transport_installed() is True
