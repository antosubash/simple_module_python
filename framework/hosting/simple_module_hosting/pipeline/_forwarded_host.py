"""Honour ``X-Forwarded-Host`` from a trusted proxy, for allowlisted hosts only (#528).

uvicorn's ``ProxyHeadersMiddleware`` corrects scheme and client address but not
the host, so behind a proxy that rewrites ``Host`` to the upstream name,
``request.url_for(...)`` and the tenants subdomain resolver see the internal
name. This middleware swaps the ``host`` header (and ``scope["server"]``) for the
forwarded one, but only when the peer is a trusted proxy *and* the value is on
the operator's allowlist: an unlisted host is ignored, so a forged header cannot
poison absolute URLs or pick a tenant.

It runs before ProxyHeaders (which replaces ``scope["client"]`` with the
forwarded client) so the peer it checks is still the proxy's TCP address.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from collections.abc import Iterable

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_WILDCARD = "*"
_SUBDOMAIN_PREFIX = "*."
_HOST_HEADER = b"host"
_FORWARDED_HOST_HEADER = b"x-forwarded-host"
_FORWARDED_PROTO_HEADER = b"x-forwarded-proto"
_DEFAULT_PORTS = {"https": 443, "wss": 443}
_FALLBACK_PORT = 80
_HOST_PATTERN = re.compile(r"^(?P<host>[a-z0-9]([a-z0-9._-]*[a-z0-9])?)(:(?P<port>\d{1,5}))?$")


def _split_host(value: str) -> tuple[str, str | None] | None:
    match = _HOST_PATTERN.match(value.strip().lower())
    return (match["host"], match["port"]) if match else None


def _forwarded_proto(scope: Scope) -> str | None:
    """Rightmost ``X-Forwarded-Proto``: ProxyHeaders has not rewritten the scheme yet."""
    raw = ",".join(v.decode("latin-1") for k, v in scope["headers"] if k == _FORWARDED_PROTO_HEADER)
    return raw.split(",")[-1].strip().lower() or None


class TrustedPeers:
    """Mirror of uvicorn's trusted-hosts rule: ``*``, IPs and CIDRs, comma-separated."""

    def __init__(self, spec: str) -> None:
        self._always = spec.strip() == _WILDCARD
        self._literals: set[str] = set()
        self._networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for item in spec.split(","):
            item = item.strip()
            if not item or item == _WILDCARD:
                continue
            try:
                self._networks.append(ipaddress.ip_network(item, strict=False))
            except ValueError:
                self._literals.add(item)  # e.g. a unix-socket peer name

    def __contains__(self, peer: str | None) -> bool:
        if self._always:
            return True
        if not peer:
            return False
        if peer in self._literals:
            return True
        try:
            address = ipaddress.ip_address(peer)
        except ValueError:
            return False
        return any(address in network for network in self._networks)


class HostAllowlist:
    """Exact hosts or ``*.example.com`` (any depth, never the apex), optional port."""

    def __init__(self, entries: Iterable[str]) -> None:
        self._exact: list[tuple[str, str | None]] = []
        self._suffixes: list[tuple[str, str | None]] = []
        for entry in entries:
            wildcard = entry.strip().lower().startswith(_SUBDOMAIN_PREFIX)
            parsed = _split_host(entry.strip()[len(_SUBDOMAIN_PREFIX) :] if wildcard else entry)
            if parsed is None:
                logger.warning("Ignoring invalid forwarded_host_allowlist entry %r", entry)
                continue
            host, port = parsed
            (self._suffixes if wildcard else self._exact).append((host, port))

    def allows(self, host: str, port: str | None) -> bool:
        def port_ok(allowed: str | None) -> bool:
            return allowed is None or allowed == port

        if any(host == name and port_ok(p) for name, p in self._exact):
            return True
        return any(host.endswith("." + name) and port_ok(p) for name, p in self._suffixes)


class ForwardedHostMiddleware:
    def __init__(self, app: ASGIApp, *, trusted_hosts: str, allowlist: Iterable[str]) -> None:
        self.app = app
        self._peers = TrustedPeers(trusted_hosts)
        self._allowed = HostAllowlist(allowlist)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            client = scope.get("client")
            if client and client[0] in self._peers:
                self._rewrite(scope)
        await self.app(scope, receive, send)

    def _rewrite(self, scope: Scope) -> None:
        raw = ",".join(
            v.decode("latin-1") for k, v in scope["headers"] if k == _FORWARDED_HOST_HEADER
        )
        if not raw:
            return
        # Rightmost value: the one our trusted proxy added. Earlier values came
        # from upstream hops or the client and cannot be trusted (an appending
        # proxy keeps whatever the client sent at the front).
        parsed = _split_host(raw.split(",")[-1])
        if parsed is None or not self._allowed.allows(*parsed):
            logger.debug("Ignoring X-Forwarded-Host %r: not on the allowlist", raw)
            return
        host, port = parsed
        value = host if port is None else f"{host}:{port}"
        scope["headers"] = [
            *((k, v) for k, v in scope["headers"] if k != _HOST_HEADER),
            (_HOST_HEADER, value.encode("latin-1")),
        ]
        proto = _forwarded_proto(scope) or scope.get("scheme", "")
        default = _DEFAULT_PORTS.get(proto, _FALLBACK_PORT)
        scope["server"] = (host, int(port) if port else default)
