"""Shared sign-in preserves browser gates, clears authority and rotates CSRF."""

from types import SimpleNamespace

import pytest
from auth.contracts.schemas import UserContext
from auth.oidc_common.session import sign_in
from simple_module_hosting.csrf import get_csrf_token
from simple_module_hosting.session import preserve_across_sign_in
from starlette.requests import Request


@pytest.mark.parametrize("identity_key", [None, "oidc_identity"])
@pytest.mark.parametrize("target,expected", [("/deep/", "/deep/"), ("//evil.test", "/home/")])
def test_rotation_and_safe_next(identity_key, target, expected):
    app = SimpleNamespace(state=SimpleNamespace())
    preserve_across_sign_in(app, "browser_gate")
    session = {
        "user_ctx": {"id": "old"},
        "browser_gate": "open",
        "next": target,
        "active_tenant_id": "old-tenant",
        "expires_at": 1,
        "old_refresh": "old",
        "oidc_session_id": "old-session-id",
    }
    request = Request({"type": "http", "app": app, "session": session})
    old_csrf = get_csrf_token(request)
    user = UserContext(id="new", email="new@example.com", name="New")
    destination = sign_in(
        request,
        user=user,
        expires_at=2000,
        redirect="/home/",
        user_key="user_ctx",
        identity_key=identity_key,
        identity=("https://issuer", "subject"),
    )
    assert destination == expected
    assert session["user_ctx"] == user.to_session_dict()
    assert session["expires_at"] == 2000
    assert session["browser_gate"] == "open"
    assert not {"next", "active_tenant_id", "old_refresh"} & session.keys()
    assert get_csrf_token(request) != old_csrf
    assert len(session["oidc_session_id"]) >= 32
    assert session["oidc_session_id"] != "old-session-id"
    if identity_key:
        assert session[identity_key] == ["https://issuer", "subject"]
