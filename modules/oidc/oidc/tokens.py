"""Sealing for the refresh token kept in the browser session.

Starlette's session cookie is signed, not encrypted, so anything stored in it
is readable by whoever holds the cookie. The refresh token is a long-lived
credential, so it is Fernet-encrypted under a key derived (HKDF) from the app's
secret key before it goes into the session.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from oidc.constants import SESSION_REFRESH_TOKEN_KEY

logger = logging.getLogger(__name__)
_HKDF_INFO = b"oidc-refresh-token"
# Browsers drop a cookie over 4096 bytes, and a dropped session cookie means a
# sign-in loop. Starlette's cookie is base64(JSON) plus a signature; keep a
# margin for the signature, the cookie name and its attributes.
_COOKIE_LIMIT_BYTES = 4096
_COOKIE_OVERHEAD_BYTES = 200


def _fernet(app: Any) -> Fernet:
    secret = app.state.sm.settings.secret_key
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(
        secret.encode()
    )
    return Fernet(base64.urlsafe_b64encode(key))


def seal_refresh_token(app: Any, token: str) -> str:
    return _fernet(app).encrypt(token.encode()).decode()


def open_refresh_token(app: Any, sealed: Any) -> str | None:
    """The plaintext token, or ``None`` if absent, tampered with or sealed under another key."""
    if not isinstance(sealed, str) or not sealed:
        return None
    try:
        return _fernet(app).decrypt(sealed.encode()).decode()
    except (InvalidToken, UnicodeError):
        return None


def store_refresh_token(app: Any, session: Any, token: str) -> bool:
    """Seal ``token`` into ``session`` if the cookie still fits, else leave it out.

    Without it the session simply ends at the ID token's expiry and the user
    signs in again. Some IdPs (Entra) issue refresh tokens large enough to
    overflow the cookie together with the principal.
    """
    session[SESSION_REFRESH_TOKEN_KEY] = seal_refresh_token(app, token)
    encoded = base64.b64encode(json.dumps(dict(session)).encode())
    if len(encoded) + _COOKIE_OVERHEAD_BYTES <= _COOKIE_LIMIT_BYTES:
        return True
    session.pop(SESSION_REFRESH_TOKEN_KEY, None)
    logger.warning("OIDC refresh token too large for the session cookie; session ends at expiry")
    return False
