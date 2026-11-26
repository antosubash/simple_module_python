"""Resolve, vet and pin SMTP destinations before handing sockets to aiosmtplib."""

import asyncio
import ipaddress
import logging
import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from typing import cast

import aiosmtplib

from mail.core.constants import SMTP_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)
_METADATA_ADDRESSES = frozenset(
    ipaddress.ip_address(address) for address in ("fd00:ec2::254", "100.100.100.200", "192.0.0.192")
)
_NAT64_V6 = ipaddress.IPv6Network("64:ff9b::/96")


def _refused(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.sixtofour is not None and _refused(str(ip.sixtofour)):
            return True
        if ip.teredo is not None and any(_refused(str(endpoint)) for endpoint in ip.teredo):
            return True
        # ipaddress labels even globally usable NAT64 destinations as reserved.
        if ip in _NAT64_V6:
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        else:
            ip = ip.ipv4_mapped or ip
    # IPv6 loopback is also classified as reserved by ipaddress.
    return not ip.is_loopback and (
        ip.is_link_local
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_reserved
        or ip in _METADATA_ADDRESSES
    )


async def _connect(host: str, port: int) -> socket.socket:
    loop = asyncio.get_running_loop()
    async with asyncio.timeout(SMTP_TIMEOUT_SECONDS):
        answers = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not answers:
            raise OSError("SMTP hostname resolved to no addresses")
        # Check every answer before opening any socket, including mixed-family DNS.
        if any(_refused(cast(str, answer[4][0])) for answer in answers):
            reason = (
                "SMTP destination refused: link-local, metadata, unspecified, "
                "multicast or reserved address"
            )
            logger.warning(reason)
            raise ValueError(reason)
        for index, (family, kind, proto, _, address) in enumerate(answers):
            sock = socket.socket(family, kind, proto)
            try:
                sock.setblocking(False)
                # Numeric sockaddr: sock_connect never resolves the configured name again.
                await loop.sock_connect(sock, address)
            except OSError:
                sock.close()
                if index == len(answers) - 1:
                    raise
            except BaseException:
                sock.close()
                raise
            else:
                return sock
    raise OSError("SMTP hostname resolved to no usable addresses")


class _SocketSMTP(aiosmtplib.SMTP):
    """Remember ownership even after aiosmtplib clears its transport on failure."""

    socket_transferred = False

    def close(self) -> None:
        # connect() also calls close() on greeting/TLS errors, clearing transport.
        self.socket_transferred |= self.transport is not None
        super().close()


@asynccontextmanager
async def _smtp_connection(
    host: str,
    port: int,
    *,
    username: str,
    password: str,
    use_tls: bool,
    start_tls: bool,
) -> AsyncGenerator[aiosmtplib.SMTP]:
    try:
        sock = await _connect(host, port)
    except TimeoutError as exc:
        raise TimeoutError("Timed out resolving or connecting to SMTP destination") from exc
    try:
        # Keep the configured hostname for TLS verification/SNI with a pinned socket.
        client = _SocketSMTP(
            hostname=host,
            sock=sock,
            use_tls=use_tls,
            start_tls=start_tls,
            timeout=SMTP_TIMEOUT_SECONDS,
        )
    except BaseException:
        sock.close()
        raise
    try:
        await client.connect()
        try:
            if username:
                await client.login(username, password)
            yield client
        finally:
            # A hangup failure must not mask a login or delivery error.
            with suppress(Exception):
                await client.quit()
    finally:
        client.close()
        if not client.socket_transferred:
            sock.close()
