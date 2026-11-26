"""SMTP serialization and handshake tests use a preconnected socket double."""

import socket
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def smtp_socket(monkeypatch):
    sock = MagicMock(spec=socket.socket)

    @asynccontextmanager
    async def connected(host, port):
        yield sock

    monkeypatch.setattr("mail.delivery.sender._smtp_socket", connected)
    return sock
