"""Fetch-metadata refusal and token validation at the browser boundary."""

import pytest
from fastapi import HTTPException, Request
from simple_module_hosting.csrf import get_csrf_token
from users.auth_local.browser_guard import require_browser_csrf


@pytest.mark.parametrize(
    ("headers", "allowed"),
    [
        ({"origin": "http://testserver:80"}, True),
        ({"origin": "https://app.example"}, True),  # proxy: scheme/host differ from base_url
        ({"referer": "http://testserver/login?next=%2F"}, True),
        ({"sec-fetch-site": "cross-site"}, False),
        ({"sec-fetch-site": "same-site"}, True),
    ],
)
async def test_browser_source_with_valid_session_token(headers, allowed):
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/users/auth/login",
            "root_path": "",
            "server": ("testserver", 80),
            "session": {},
            "headers": [(b"host", b"testserver")],
        }
    )
    token = get_csrf_token(request)
    request.scope["headers"].extend(
        (name.encode(), value.encode())
        for name, value in {**headers, "x-csrf-token": token}.items()
    )
    # Request.headers may already be cached by URL construction.
    request = Request(request.scope)
    if allowed:
        await require_browser_csrf(request)
    else:
        with pytest.raises(HTTPException) as error:
            await require_browser_csrf(request)
        assert error.value.status_code == 403
