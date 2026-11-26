"""Exercise the real SMTP handshake over an in-memory transport (#1073)."""

import asyncio
import ssl
from unittest.mock import AsyncMock

import aiosmtplib
import pytest
from mail.delivery.sender import SmtpMailSender
from simple_module_core.mailer.mail import MailMessage


@pytest.mark.parametrize("implicit", [False, True])
@pytest.mark.parametrize("operation", ["verify", "send"])
async def test_pinned_socket_keeps_tls_hostname_and_certificate_verification(
    monkeypatch, smtp_socket, implicit, operation
):
    loop = asyncio.get_running_loop()
    commands = []
    options = []
    upgrades = []

    class Peer(asyncio.Transport):
        def __init__(self, protocol):
            self.protocol = protocol
            self.closed = False
            self.receiving_data = False

        def get_extra_info(self, name, default=None):
            return default

        def is_closing(self):
            return self.closed

        def write(self, data):
            command = "BODY" if self.receiving_data else data.split()[0].decode().upper()
            self.receiving_data = command == "DATA"
            commands.append(command)
            reply = {
                "EHLO": b"250-localhost\r\n250 STARTTLS\r\n",
                "STARTTLS": b"220 ready for TLS\r\n",
                "QUIT": b"221 bye\r\n",
                "MAIL": b"250 sender OK\r\n",
                "RCPT": b"250 recipient OK\r\n",
                "DATA": b"354 send message\r\n",
                "BODY": b"250 accepted\r\n",
            }[command]
            loop.call_soon(self.protocol.data_received, reply)

        def close(self):
            if not self.closed:
                self.closed = True
                self.protocol.connection_lost(None)

    async def connect(factory, **kwargs):
        options.append(kwargs)
        protocol = factory()
        transport = Peer(protocol)
        protocol.connection_made(transport)
        protocol.data_received(b"220 localhost SMTP ready\r\n")
        return transport, protocol

    async def upgrade(transport, protocol, context, **kwargs):
        upgrades.append((context, kwargs))
        return transport

    async def tls_context(client):
        # Exercise the real certificate settings without sandbox thread wakeups.
        return client._build_tls_context()

    monkeypatch.setattr(aiosmtplib.SMTP, "_get_tls_context", tls_context)
    monkeypatch.setattr(
        aiosmtplib.SMTP, "_get_default_local_hostname", AsyncMock(return_value="localhost")
    )
    monkeypatch.setattr(loop, "create_connection", connect)
    monkeypatch.setattr(loop, "start_tls", upgrade)
    sender = SmtpMailSender(
        "relay.test",
        1465 if implicit else 587,
        "",
        "",
        "from@test",
        True,
        tls_mode="implicit" if implicit else "starttls",
    )
    work = (
        sender.send(MailMessage("to@test", "Hi", "Body"))
        if operation == "send"
        else sender.verify_connection()
    )
    await asyncio.wait_for(work, timeout=5)
    assert options[0]["sock"] is smtp_socket
    assert "host" not in options[0] and "port" not in options[0]
    if implicit:
        context, tls_options = options[0]["ssl"], options[0]
        assert not upgrades
    else:
        assert options[0]["ssl"] is None
        ((context, tls_options),) = upgrades
    assert tls_options["server_hostname"] == "relay.test"
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    expected = [] if implicit else ["EHLO", "STARTTLS"]
    if operation == "send":
        expected += ["EHLO", "MAIL", "RCPT", "DATA", "BODY"]
    assert commands == [*expected, "QUIT"]
