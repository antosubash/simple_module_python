"""Provider-scoped refresh-token encryption; preserves existing session ciphertext."""

from typing import Any

from auth.oidc_common import tokens

from oidc.constants import SESSION_REFRESH_TOKEN_KEY

_HKDF_INFO = b"oidc-refresh-token"


def seal_refresh_token(app: Any, token: str) -> str:
    return tokens.seal_refresh_token(app, token, info=_HKDF_INFO)


def open_refresh_token(app: Any, sealed: Any) -> str | None:
    return tokens.open_refresh_token(app, sealed, info=_HKDF_INFO)


def store_refresh_token(app: Any, session: Any, token: str) -> bool:
    return tokens.store_refresh_token(
        app, session, token, info=_HKDF_INFO, session_key=SESSION_REFRESH_TOKEN_KEY
    )
