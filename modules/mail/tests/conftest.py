"""SMTP tests use a preconnected socket double instead of external networking."""

import socket
from unittest.mock import AsyncMock, MagicMock

import pytest
from mail.delivery._destination import _SocketSMTP


@pytest.fixture
def smtp_socket(monkeypatch):
    sock = MagicMock(spec=socket.socket)
    monkeypatch.setattr("mail.delivery._destination._connect", AsyncMock(return_value=sock))
    return sock


@pytest.fixture
def smtp_delivery(monkeypatch, smtp_socket):
    for method in ("connect", "login", "quit"):
        monkeypatch.setattr(_SocketSMTP, method, AsyncMock())
