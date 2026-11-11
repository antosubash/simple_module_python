"""Write the IdP's profile onto the OAuth link after a sign-in (#877)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlmodel import col

from users.models import OAuthAccount, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from users.oauth.identity import OAuthIdentity

_LINK_TEXT_MAX = 320
_FULL_NAME_MAX = 255


async def record_profile(
    session: AsyncSession,
    user: User,
    provider: str,
    identity: OAuthIdentity,
    *,
    created: bool,
    sync_name: bool,
) -> None:
    """Refresh the link's profile and ``last_sign_in_at``; set ``full_name`` if due.

    ``full_name`` comes from the IdP's display name when this sign-in created
    the account, and on later sign-ins only with ``sync_name``. It is never
    cleared, and the account email is never touched (unique-email collisions).
    Flushed, not committed: the request session commits after the response.
    """
    stmt = select(OAuthAccount).where(
        col(OAuthAccount.user_id) == user.id,
        col(OAuthAccount.oauth_name) == provider,
        col(OAuthAccount.account_id) == identity.account_id,
    )
    link = (await session.execute(stmt)).scalar_one_or_none()
    if link is not None:
        link.subject = _clip(identity.subject, _LINK_TEXT_MAX)
        link.username = _clip(identity.username, _LINK_TEXT_MAX)
        link.display_name = _clip(identity.display_name, _LINK_TEXT_MAX)
        link.extra = identity.extra or None
        link.last_sign_in_at = datetime.now(UTC)
    name = _clip(identity.display_name, _FULL_NAME_MAX)
    if name and (sync_name or (created and not user.full_name)) and user.full_name != name:
        user.full_name = name
    await session.flush()


def _clip(value: str | None, limit: int) -> str | None:
    value = value.strip() if value else None
    return value[:limit] if value else None
