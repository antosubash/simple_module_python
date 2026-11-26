"""Pinned sockets must outlive deferred asyncio transport shutdown (#1228)."""

import asyncio
import socket
from unittest.mock import AsyncMock

import aiosmtplib
import pytest
from mail.delivery.sender import SmtpMailSender
from simple_module_core.mailer.mail import MailMessage


@pytest.mark.parametrize("operation", ["send", "verify"])
@pytest.mark.parametrize("failure", [None, "greeting", "login"])
async def test_transport_owns_socket_until_deferred_shutdown(monkeypatch, operation, failure):
    loop = asyncio.get_running_loop()
    sock, peer = socket.socketpair()
    sock.setblocking(False)
    fd = sock.fileno()
    monkeypatch.setattr("mail.delivery._destination._connect", AsyncMock(return_value=sock))
    monkeypatch.setattr(
        aiosmtplib.SMTP, "_get_default_local_hostname", AsyncMock(return_value="localhost")
    )
    create_connection = loop.create_connection
    transports = []
    shutdowns = []
    close_requests = []

    async def connect(factory, **kwargs):
        transport, protocol = await create_connection(factory, **kwargs)
        transports.append(transport)
        shutdowns.append(transport.close)
        # Model TLS waiting for its peer: close is requested, but the real selector
        # transport retains the fd until the test allows shutdown to finish.
        monkeypatch.setattr(transport, "close", lambda: close_requests.append(transport))
        receiving_body = False

        def write(data):
            nonlocal receiving_body
            command = "BODY" if receiving_body else data.split()[0].decode().upper()
            receiving_body = command == "DATA"
            reply = {
                "EHLO": b"250 localhost\r\n",
                "MAIL": b"250 OK\r\n",
                "RCPT": b"250 OK\r\n",
                "DATA": b"354 continue\r\n",
                "BODY": b"250 accepted\r\n",
                "QUIT": b"221 bye\r\n",
            }[command]
            loop.call_soon(protocol.data_received, reply)

        monkeypatch.setattr(transport, "write", write)
        protocol.data_received(b"554 refused\r\n" if failure == "greeting" else b"220 ready\r\n")
        return transport, protocol

    monkeypatch.setattr(loop, "create_connection", connect)
    if failure == "login":
        monkeypatch.setattr(
            aiosmtplib.SMTP, "login", AsyncMock(side_effect=ValueError("login failed"))
        )
        monkeypatch.setattr(
            aiosmtplib.SMTP, "quit", AsyncMock(side_effect=RuntimeError("quit failed"))
        )
    sender = SmtpMailSender(
        "relay.test", 587, "user" if failure == "login" else "", "pw", "a@test", False
    )
    replacement = None
    try:
        async with asyncio.timeout(5):
            try:
                if operation == "send":
                    await sender.send(MailMessage("b@test", "Hi", "Body"))
                else:
                    await sender.verify_connection()
            except (aiosmtplib.SMTPConnectResponseError, ValueError) as exc:
                assert failure is not None
                if failure == "login":
                    assert str(exc) == "login failed"
            else:
                assert failure is None
        replacement, replacement_peer = socket.socketpair()
        try:
            # With the bug this fd is reused while still registered to the old
            # transport, and add_reader raises "is used by transport".
            loop.add_reader(replacement.fileno(), lambda: None)
            loop.remove_reader(replacement.fileno())
            assert replacement.fileno() != fd
            assert sock.fileno() == fd
            assert not transports[0].is_closing()
            assert close_requests
        finally:
            replacement_peer.close()
    finally:
        for shutdown in shutdowns:
            shutdown()
        # Wait for the real connection_lost callback, without sleeping.
        done = loop.create_future()
        loop.call_soon(done.set_result, None)
        await done
        sock.close()
        peer.close()
        if replacement is not None:
            replacement.close()


@pytest.mark.parametrize("operation", ["send", "verify"])
async def test_socket_closes_if_transport_creation_fails(monkeypatch, operation):
    sock, peer = socket.socketpair()
    monkeypatch.setattr("mail.delivery._destination._connect", AsyncMock(return_value=sock))
    monkeypatch.setattr(
        aiosmtplib.SMTP, "_get_default_local_hostname", AsyncMock(return_value="localhost")
    )
    monkeypatch.setattr(
        asyncio.get_running_loop(),
        "create_connection",
        AsyncMock(side_effect=ValueError("no transport")),
    )
    sender = SmtpMailSender("relay.test", 587, "", "", "a@test", False)
    try:
        with pytest.raises(ValueError, match="no transport"):
            if operation == "send":
                await sender.send(MailMessage("b@test", "Hi", "Body"))
            else:
                await sender.verify_connection()
        assert sock.fileno() == -1
    finally:
        sock.close()
        peer.close()
