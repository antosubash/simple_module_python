"""SMTP destination policy applies before either delivery or diagnostics (#1228)."""

import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock

import pytest
from mail.delivery.runtime import check_smtp
from mail.delivery.sender import SmtpMailSender
from simple_module_core.mailer.mail import MailMessage, install_mail_sender
from simple_module_core.web.health import HealthStatus


def _answer(ip):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    address = (ip, 587, 0, 0) if family == socket.AF_INET6 else (ip, 587)
    return family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", address


@pytest.fixture
async def network(monkeypatch):
    loop = asyncio.get_running_loop()
    resolve = AsyncMock(return_value=[_answer("10.0.0.25")])
    connect = AsyncMock()
    sockets = MagicMock(side_effect=lambda *args: MagicMock(spec=socket.SocketType))
    monkeypatch.setattr(loop, "getaddrinfo", resolve)
    monkeypatch.setattr(loop, "sock_connect", connect)
    monkeypatch.setattr(socket, "socket", sockets)
    send = AsyncMock()
    client = AsyncMock()
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.SMTP", MagicMock(return_value=client))
    return resolve, connect, sockets, send, client


async def _run(operation):
    sender = SmtpMailSender("relay.test", 587, "", "", "from@test", False)
    if operation == "send":
        await sender.send(MailMessage("to@test", "Hi", "Body"))
    else:
        await sender.verify_connection()


@pytest.mark.parametrize("operation", ["send", "verify"])
@pytest.mark.parametrize(
    "ip",
    [
        "169.254.169.254",
        "169.254.1.1",
        "fe80::1",
        "febf::1",
        "fe80::1%eth0",
        "fd00:ec2::254",
        "fd00:ec2::254%1",
        "100.100.100.200",
        "192.0.0.192",
        "::ffff:100.100.100.200",
        "64:ff9b::6464:64c8",
        "2002:6464:64c8::1",
        "0.0.0.0",
        "::",
        "224.0.0.1",
        "ff02::1",
        "240.0.0.1",
        "255.255.255.255",
        "100::1",
        "::ffff:169.254.169.254",
        "::ffff:0.0.0.0",
        "::ffff:224.0.0.1",
        "::169.254.169.254",
        "64:ff9b::a9fe:a9fe",
        "2002:a9fe:a9fe::1",
        "2001:0:808:808:0:ffff:5601:5601",
        "2001:0:a9fe:a9fe:0:ffff:f7f7:f7f7",
    ],
)
async def test_refused_address_never_connects(network, ip, operation):
    resolve, connect, sockets, send, client = network
    resolve.return_value = [_answer(ip)]
    with pytest.raises(ValueError, match="SMTP destination refused"):
        await _run(operation)
    sockets.assert_not_called()
    connect.assert_not_awaited()
    send.assert_not_awaited()
    client.connect.assert_not_awaited()


@pytest.mark.parametrize("operation", ["send", "verify"])
@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "::1",
        "10.0.0.25",
        "172.16.0.1",
        "192.168.1.1",
        "fd00::1",
        "8.8.8.8",
        "2606:4700:4700::1111",
        "::ffff:127.0.0.1",
        "64:ff9b::808:808",
        "64:ff9b::a00:19",
        "2002:808:808::1",
        "2001:0:808:808:0:ffff:f7f7:f7f7",
    ],
)
async def test_allowed_address_is_pinned_to_connected_socket(network, ip, operation):
    resolve, connect, _, send, _ = network
    resolve.return_value = [_answer(ip)]
    await _run(operation)
    resolve.assert_awaited_once_with("relay.test", 587, type=socket.SOCK_STREAM)
    sock, address = connect.call_args.args
    assert address == _answer(ip)[4]
    sock.setblocking.assert_called_once_with(False)
    sock.close.assert_called_once()
    if operation == "send":
        kwargs = send.call_args.kwargs
    else:
        from mail.delivery import sender

        kwargs = sender.aiosmtplib.SMTP.call_args.kwargs
    assert kwargs["sock"] is sock
    assert kwargs["hostname"] == "relay.test"
    assert "port" not in kwargs


@pytest.mark.parametrize("operation", ["send", "verify"])
@pytest.mark.parametrize("reverse", [False, True])
async def test_any_refused_dns_answer_blocks_the_whole_host(network, operation, reverse):
    resolve, connect, sockets, _, _ = network
    answers = [_answer("10.0.0.25"), _answer("fd00:ec2::254")]
    resolve.return_value = answers[::-1] if reverse else answers
    with pytest.raises(ValueError, match="SMTP destination refused"):
        await _run(operation)
    connect.assert_not_awaited()
    sockets.assert_not_called()


async def test_refusal_is_clear_in_diagnostics_and_logged_without_message_content(network, caplog):
    network[0].return_value = [_answer("169.254.169.254")]
    sender = SmtpMailSender("relay.test", 587, "user", "secret", "from@test", True)
    install_mail_sender(sender)
    result = await check_smtp()
    assert result.status is HealthStatus.UNHEALTHY
    assert "SMTP destination refused" in result.detail
    with pytest.raises(ValueError):
        await sender.send(MailMessage("private@test", "Private subject", "Private body"))
    assert "SMTP destination refused" in caplog.text
    assert all(value not in caplog.text for value in ["secret", "private@test", "Private body"])


async def test_failed_first_address_falls_back_only_to_another_vetted_address(network):
    resolve, connect, _, send, _ = network
    resolve.return_value = [_answer("::1"), _answer("127.0.0.1")]
    connect.side_effect = [ConnectionRefusedError(), None]
    await _run("send")
    assert [call.args[1] for call in connect.call_args_list] == [
        ("::1", 587, 0, 0),
        ("127.0.0.1", 587),
    ]
    assert send.call_args.kwargs["sock"] is connect.call_args.args[0]
    for call in connect.call_args_list:
        call.args[0].close.assert_called_once()


@pytest.mark.parametrize("operation", ["send", "verify"])
async def test_socket_is_closed_when_smtp_fails(network, operation):
    _, connect, _, send, client = network
    send.side_effect = client.connect.side_effect = RuntimeError("SMTP failed")
    with pytest.raises(RuntimeError, match="SMTP failed"):
        await _run(operation)
    connect.call_args.args[0].close.assert_called_once()


@pytest.mark.parametrize("error", [ConnectionRefusedError(), asyncio.CancelledError()])
async def test_socket_is_closed_when_tcp_connect_fails_or_is_cancelled(network, error):
    _, connect, _, _, _ = network
    connect.side_effect = error
    with pytest.raises(type(error)):
        await _run("verify")
    connect.call_args.args[0].close.assert_called_once()


async def test_empty_dns_answer_does_not_connect(network):
    resolve, connect, sockets, _, _ = network
    resolve.return_value = []
    with pytest.raises(OSError, match="no addresses"):
        await _run("verify")
    sockets.assert_not_called()
    connect.assert_not_awaited()


@pytest.mark.parametrize("stage", ["dns", "connect"])
async def test_destination_timeout_has_a_safe_diagnostic_and_closes_socket(
    network, monkeypatch, stage
):
    from mail.delivery import _destination

    async def blocked(*args, **kwargs):
        await asyncio.Future()

    monkeypatch.setattr(_destination, "SMTP_TIMEOUT_SECONDS", 0)
    resolve, connect, sockets, _, _ = network
    (resolve if stage == "dns" else connect).side_effect = blocked
    install_mail_sender(SmtpMailSender("relay.test", 587, "", "", "from@test", False))
    result = await check_smtp()
    assert result.status is HealthStatus.UNHEALTHY
    assert "timed out" in result.detail.lower()
    assert "relay.test" not in result.detail and "10.0.0.25" not in result.detail
    if stage == "dns":
        sockets.assert_not_called()
    else:
        connect.call_args.args[0].close.assert_called_once()


@pytest.mark.parametrize(
    "host", ["2852039166", "0251.0376.0251.0376", "0xa9fea9fe", "169.254.43518", "fe80::1%1"]
)
async def test_libc_numeric_host_forms_cannot_bypass_the_policy(network, host):
    resolve, connect, sockets, _, _ = network
    # Numeric-only libc lookup exercises normalization without an external DNS request.
    resolve.side_effect = lambda host, port, **kwargs: socket.getaddrinfo(
        host, port, flags=socket.AI_NUMERICHOST, **kwargs
    )
    sender = SmtpMailSender(host, 587, "", "", "from@test", False)
    with pytest.raises(ValueError, match="SMTP destination refused"):
        await sender.verify_connection()
    sockets.assert_not_called()
    connect.assert_not_awaited()


@pytest.mark.parametrize("ip", ["8.8.8.8", "2606:4700:4700::1111", "::ffff:8.8.8.8"])
async def test_real_sock_connect_does_not_repeat_dns_after_vetting(network, monkeypatch, ip):
    resolve, _, sockets, _, _ = network
    resolve.side_effect = [[_answer(ip)], [_answer("169.254.169.254")]]
    loop = asyncio.get_running_loop()
    connected = []

    def socket_double(family, kind, proto):
        sock = MagicMock(spec=socket.SocketType)
        sock.family, sock.type, sock.proto = family, kind, proto
        return sock

    def connected_without_io(future, sock, address):
        connected.append(address)
        future.set_result(None)

    sockets.side_effect = socket_double
    # Keep asyncio's numeric-address fast path; stub only the final OS operation.
    monkeypatch.setattr(loop, "sock_connect", type(loop).sock_connect.__get__(loop))
    monkeypatch.setattr(loop, "_sock_connect", connected_without_io)
    await _run("verify")
    assert connected == [_answer(ip)[4]]
    assert resolve.await_count == 1
