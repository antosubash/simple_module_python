"""Warn once when a ``Secure`` session cookie is served over plain HTTP (#495).

Outside development the session cookie is ``Secure``. A browser that reaches
the app over ``http://`` on a real hostname never sends it back, so sign-in
bounces to the login page with nothing in the logs. This names the two
settings that fix it, once per process.

Loopback hosts are exempt: browsers treat ``http://localhost`` as a secure
context and keep ``Secure`` cookies there. The check runs after
``ProxyHeaders``, so an install with ``SM_TRUSTED_PROXY`` set sees the
forwarded ``https`` scheme and never warns.
"""

from __future__ import annotations

import logging
from ipaddress import ip_address

from starlette.types import Scope

logger = logging.getLogger("simple_module_hosting.session")

_warned = False


def warn_if_plain_http(scope: Scope) -> None:
    """Log one WARNING per process for an ``http`` request to a non-loopback host."""
    global _warned
    if _warned or scope.get("scheme") != "http":
        return
    host = _host(scope)
    if host is None or _is_loopback(host):
        return
    _warned = True
    logger.warning(
        "Request for %r arrived over plain HTTP, but the session cookie is Secure: "
        "browsers will not send it back and sign-in will fail. Behind a TLS-terminating "
        "proxy set SM_TRUSTED_PROXY so the forwarded https scheme is trusted; to serve "
        "browsers over plain HTTP on purpose set SM_SESSION_COOKIE_SECURE=false.",
        host,
    )


def _host(scope: Scope) -> str | None:
    for key, value in scope.get("headers") or ():
        if key == b"host":
            raw = value.decode("latin-1").strip().lower()
            if raw.startswith("["):  # [::1]:8000
                return raw[1 : raw.find("]")] if "]" in raw else None
            return raw.rsplit(":", 1)[0] if raw.count(":") == 1 else raw
    server = scope.get("server")
    return str(server[0]).lower() if server else None


def _is_loopback(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _reset_for_tests() -> None:
    global _warned
    _warned = False
