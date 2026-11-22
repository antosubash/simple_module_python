"""Helpers for forging signed Starlette session cookies in tests.

Starlette's ``SessionMiddleware`` encodes sessions as base64-encoded JSON
signed with an ``itsdangerous`` ``TimestampSigner``. Tests that want to
skip the HTTP flow (login / locale-switcher / etc.) to establish a session
can call :func:`forge_session_cookie` to build the exact cookie value the
middleware would emit, then inject it via ``httpx.AsyncClient(cookies=...)``.
"""

from __future__ import annotations

import json
from base64 import b64encode

from itsdangerous import TimestampSigner


def forge_session_cookie(secret_key: str, session_data: dict) -> str:
    """Return the signed cookie value Starlette's SessionMiddleware would emit.

    The encoding (``b64(json)`` signed with ``TimestampSigner``) must match
    Starlette exactly — otherwise the middleware rejects the cookie and the
    test request arrives with an empty session.
    """
    data = b64encode(json.dumps(session_data).encode())
    return TimestampSigner(str(secret_key)).sign(data).decode("utf-8")
