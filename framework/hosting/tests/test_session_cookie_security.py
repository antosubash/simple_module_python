"""SameSite/HttpOnly invariants for the framework's session cookie.

CLAUDE.md treats SameSite=Lax as the CSRF defence — there is no explicit
token middleware. If a future Starlette upgrade silently switched the
default to ``None`` (used to be the case on older versions), CSRF
protection would evaporate without any test catching it.

The session cookie is also Set-Cookie'd with HttpOnly so a successful XSS
can't directly exfiltrate the user_id+user_ctx blob.
"""

from __future__ import annotations

import httpx
import pytest


def _set_cookie_for(name: str, response: httpx.Response) -> str:
    """Return the raw Set-Cookie header for ``name`` (or '' if absent).

    httpx joins multiple Set-Cookie headers with ', ' which makes
    ``response.headers.get`` ambiguous for cookies whose value contains a
    comma. We walk the raw header list instead.
    """
    for header_name, header_value in response.headers.multi_items():
        if header_name.lower() == "set-cookie" and header_value.startswith(f"{name}="):
            return header_value
    return ""


@pytest.mark.anyio
async def test_session_cookie_is_samesite_lax_and_httponly(client) -> None:
    """Any response that creates the session cookie must mark it Lax + HttpOnly.

    A GET ``/`` reliably trips ``SessionMiddleware.save()`` because every
    request flows through the middleware stack regardless of route handler.
    """
    resp = await client.get("/")
    raw = _set_cookie_for("session", resp)

    assert raw, "GET / didn't set the session cookie — has SessionMiddleware been removed?"
    lowered = raw.lower()
    assert "samesite=lax" in lowered, (
        f"Session cookie missing SameSite=Lax — CSRF defence weakened. Raw: {raw!r}"
    )
    assert "httponly" in lowered, (
        f"Session cookie missing HttpOnly — exposes user_id to XSS. Raw: {raw!r}"
    )
