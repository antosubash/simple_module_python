"""Read an invite token without spending it.

The accept-invite card asked for a password while showing neither who the
invite was for nor what access it grants. Someone forwarded a link, or holding
two invites to different deployments, had no way to tell them apart — and no
way to notice an invite addressed to the wrong person before accepting it.

``UserManager.verify`` cannot answer this: it marks the account verified as a
side effect, so calling it to peek would consume the invite. The verification
token is a JWT carrying ``sub`` and ``email``, so decoding it read-only gives
the same facts with no side effects.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import jwt
from fastapi_users.jwt import decode_jwt

logger = logging.getLogger(__name__)


def _expires_at(claims: dict[str, Any]) -> str | None:
    """The token's ``exp`` as an ISO timestamp, for the card's "Expires" row.

    Absent or unparseable means the row is simply left out — an invite with no
    stated expiry is better than an invented one.
    """
    exp = claims.get("exp")
    if not isinstance(exp, int | float):
        return None
    return datetime.fromtimestamp(exp, UTC).isoformat()


async def preview_invite(token: str, user_manager: Any) -> dict[str, Any] | None:
    """Return the invite's facts for *token*, or ``None`` if unreadable.

    ``None`` covers expired, tampered, and wrong-audience tokens alike. The
    page deliberately does not distinguish them: the reason belongs to the
    accept attempt, which validates properly.
    """
    if not token:
        return None

    try:
        data = decode_jwt(
            token,
            user_manager.verification_token_secret,
            [user_manager.verification_token_audience],
        )
    except jwt.PyJWTError:
        return None

    email = data.get("email")
    if not email:
        return None

    # Minted by the admin flow, absent from tokens issued by self-service
    # verification and from any invite created before the claim existed —
    # so the headline falls back to naming no one rather than guessing.
    invited_by_name = data.get("invited_by") or None
    expires_at = _expires_at(data)

    roles: list[str] = []
    try:
        user = await user_manager.get_by_email(email)
    except Exception:
        # The token decoded but the account is gone. Showing the address it
        # was issued for is still more useful than showing nothing; accepting
        # will fail with a proper message.
        return {
            "email": email,
            "roles": roles,
            "already_accepted": False,
            "invited_by_name": invited_by_name,
            "expires_at": expires_at,
            "full_name": None,
        }

    roles = sorted(role.name for role in getattr(user, "roles", []) or [])
    return {
        "email": email,
        "roles": roles,
        # An invite that has already been used should say so, rather than
        # presenting a password form that is guaranteed to fail.
        "already_accepted": bool(getattr(user, "is_verified", False)),
        "invited_by_name": invited_by_name,
        "expires_at": expires_at,
        # Pre-fills the "Full name" field: an admin who typed the invitee's
        # name when minting the invite should not make them type it again.
        "full_name": getattr(user, "full_name", None),
    }
