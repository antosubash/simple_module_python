"""Sealing for the refresh token kept in the browser session.

Starlette's session cookie is signed, not encrypted, so anything stored in it
is readable by whoever holds the cookie. The refresh token is a long-lived
credential, so it is Fernet-encrypted under a key derived (HKDF) from the app's
secret key before it goes into the session.
"""

from __future__ import annotations

import base64
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SESSION_REFRESH_TOKEN_KEY = "keycloak_refresh_token"
_HKDF_INFO = b"keycloak-refresh-token"


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
