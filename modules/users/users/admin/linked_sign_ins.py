"""The external sign-ins linked to an account, for the admin Edit page (#877)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from users.models import OAuthAccount


async def linked_sign_ins_for(
    request: Request, user_id: uuid.UUID, db: AsyncSession
) -> list[dict[str, Any]]:
    """Provider, IdP username, subject and last sign-in per link, read-only."""
    stmt = (
        select(
            OAuthAccount.oauth_name,
            OAuthAccount.username,
            OAuthAccount.subject,
            OAuthAccount.last_sign_in_at,
        )
        .where(col(OAuthAccount.user_id) == user_id)
        .order_by(col(OAuthAccount.oauth_name))
    )
    clients = request.app.state.users.oauth_clients
    return [
        {
            "provider": clients[name].display_name if name in clients else name,
            "username": username,
            "subject": subject,
            "last_sign_in_at": last.isoformat() if last else None,
        }
        for name, username, subject, last in (await db.execute(stmt)).all()
    ]
