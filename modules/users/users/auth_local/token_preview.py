"""Read reset and verification tokens on GET, before anything is spent.

Both screens used to learn the token was dead only after the person had typed
a new password and pressed submit, and the verify screen had no way to offer
"send me another" because it did not know the address. The tokens themselves
carry both answers, so the view decodes them read-only and hands the page a
decided state instead of a form that is guaranteed to fail.

Sibling of :mod:`users.auth_local.invite_preview`, which does the same for the
invite card; kept apart because that one also reads the account's roles.
"""

from __future__ import annotations

import logging
from typing import Any

import jwt

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"
RESET_TOKEN_AUDIENCE = "fastapi-users:reset"
VERIFY_TOKEN_AUDIENCE = "fastapi-users:verify"


def _decode(
    token: str,
    secret: str,
    audience: str,
    *,
    verify_exp: bool,
) -> dict[str, Any] | None:
    """Return the claims of *token*, or ``None`` when it cannot be trusted.

    ``None`` covers tampered, wrong-audience and (when ``verify_exp``) expired
    tokens alike. Nothing here decides an outcome — the page shows a dead-link
    card, and the endpoint that actually spends the token validates properly.
    """
    if not token:
        return None
    try:
        return jwt.decode(
            token,
            secret,
            audience=audience,
            algorithms=[_ALGORITHM],
            options={"verify_exp": verify_exp},
        )
    except jwt.PyJWTError:
        return None


def decode_reset_token(
    token: str, secret: str, *, verify_exp: bool = True
) -> dict[str, Any] | None:
    """Claims of a password-reset token: ``sub``, ``password_fgpt``, ``exp``.

    Expiry is checked by default — a reset link that has run out is exactly
    what the "Link expired" card exists to report.
    """
    return _decode(token, secret, RESET_TOKEN_AUDIENCE, verify_exp=verify_exp)


def decode_verify_token(
    token: str, secret: str, *, verify_exp: bool = False
) -> dict[str, Any] | None:
    """Claims of an email-verification token: ``sub``, ``email``, ``exp``.

    Expiry is *not* checked by default. The whole point of reading an expired
    verification link is to recover the address it was issued for, so that
    "Resend verification" can offer to send another one there rather than
    asking someone to retype the address they already gave.
    """
    return _decode(token, secret, VERIFY_TOKEN_AUDIENCE, verify_exp=verify_exp)


async def preview_reset(token: str, user_manager: Any) -> dict[str, Any] | None:
    """Return ``{"email"}`` for a live reset token, or ``None`` if it is dead.

    The token carries only the user id — fastapi-users mints it that way — so
    the address comes from the account. It is needed because "Save and sign in"
    signs the person in immediately after the reset, and asking them to retype
    the address they just proved control of would be theatre.
    """
    claims = decode_reset_token(token, user_manager.reset_password_token_secret)
    if claims is None:
        return None

    user_id = claims.get("sub")
    if not user_id:
        return None

    try:
        user = await user_manager.get(user_manager.parse_id(user_id))
    except Exception:
        # Decoded but the account is gone: treat it as a dead link rather than
        # rendering a password form nothing can accept.
        return None

    return {"email": user.email}
