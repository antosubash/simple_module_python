"""Shared sign-in rotation and callback transaction checks."""

import base64
import hashlib
import secrets
from dataclasses import dataclass

from fastapi import HTTPException, Request
from simple_module_core.redirect_safety import SESSION_NEXT_KEY, safe_next_or_none
from simple_module_hosting.csrf import rotate_csrf_token
from simple_module_hosting.session import SESSION_EXPIRES_AT_KEY, sign_in_preserved_keys
from starlette.responses import RedirectResponse

from auth.constants import SESSION_ID_KEY


@dataclass(frozen=True)
class SessionKeys:
    user: str
    refresh: str
    retry: str
    attempted: str
    identity: str | None = None
    obsolete: tuple[str, ...] = ()

    def forget(self, session) -> None:
        for key in (
            SESSION_ID_KEY,
            self.user,
            self.refresh,
            self.retry,
            self.identity,
            SESSION_EXPIRES_AT_KEY,
            *self.obsolete,
        ):
            if key is not None:
                session.pop(key, None)


def pkce_challenge(verifier: str) -> str:
    """The S256 ``code_challenge`` for a PKCE ``code_verifier``."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def stale_callback(request: Request, state_key: str, user_key: str, redirect: str):
    """Compare before consuming: a stale reply cannot destroy a pending login."""
    state = request.query_params.get("state")
    expected = request.session.get(state_key)
    if (
        state
        and isinstance(expected, str)
        and secrets.compare_digest(state.encode(), expected.encode())
    ):
        return None
    if isinstance(request.session.get(user_key), dict):
        return RedirectResponse(redirect, 303)
    # 419 "Page expired": the framework renders it with a sign-in link.
    raise HTTPException(status_code=419, detail="Sign-in expired; start again")


def sign_in(
    request: Request,
    *,
    user,
    expires_at: int,
    redirect: str,
    user_key: str,
    identity_key: str | None = None,
    identity: tuple[str, ...] = (),
) -> str:
    next_url = safe_next_or_none(request.session.pop(SESSION_NEXT_KEY, None)) or redirect
    preserved = {
        key: request.session[key]
        for key in sign_in_preserved_keys(request.app)
        if key in request.session
    }
    request.session.clear()
    request.session.update(preserved)
    request.session[SESSION_ID_KEY] = secrets.token_urlsafe(24)
    rotate_csrf_token(request)
    request.session[user_key] = user.to_session_dict()
    if identity_key is not None:
        request.session[identity_key] = list(identity)
    request.session[SESSION_EXPIRES_AT_KEY] = expires_at
    return next_url
