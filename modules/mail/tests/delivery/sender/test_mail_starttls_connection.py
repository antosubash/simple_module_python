"""Exercise the real SMTP handshake over an in-memory transport (#1073)."""

import asyncio

from mail.delivery.sender import SmtpMailSender


async def test_submission_connection_upgrades_after_plaintext_greeting(monkeypatch):
    loop = asyncio.get_running_loop()
    commands = []
    options = []
    upgrades = []

    class Peer(asyncio.Transport):
        def __init__(self, protocol):
            self.protocol = protocol
            self.closed = False

        def get_extra_info(self, name, default=None):
            return default

        def is_closing(self):
            return self.closed

        def write(self, data):
            command = data.split()[0].decode().upper()
            commands.append(command)
            reply = {
                "EHLO": b"250-localhost\r\n250 STARTTLS\r\n",
                "STARTTLS": b"220 ready for TLS\r\n",
                "QUIT": b"221 bye\r\n",
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
        upgrades.append(context)
        return transport

    monkeypatch.setattr(loop, "create_connection", connect)
    monkeypatch.setattr(loop, "start_tls", upgrade)
    await asyncio.wait_for(
        SmtpMailSender("localhost", 587, "", "", "from@test", True).verify_connection(),
        timeout=5,
    )
    assert options[0]["ssl"] is None
    assert options[0]["port"] == 587
    assert commands == ["EHLO", "STARTTLS", "QUIT"]
    assert len(upgrades) == 1
