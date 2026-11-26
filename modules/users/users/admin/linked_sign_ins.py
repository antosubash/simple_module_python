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
) -> tuple[list[dict[str, Any]], bool]:
    """Display links with stable row IDs, plus duplicate raw-provider detection."""
    stmt = (
        select(
            OAuthAccount.id,
            OAuthAccount.oauth_name,
            OAuthAccount.username,
            OAuthAccount.subject,
            OAuthAccount.last_sign_in_at,
        )
        .where(col(OAuthAccount.user_id) == user_id)
        .order_by(col(OAuthAccount.oauth_name))
    )
    clients = request.app.state.users.oauth_clients
    rows = (await db.execute(stmt)).all()
    names = [row.oauth_name for row in rows]
    return [
        {
            "id": str(link_id),
            "provider": clients[name].display_name if name in clients else name,
            "username": username,
            "subject": subject,
            "last_sign_in_at": last.isoformat() if last else None,
        }
        for link_id, name, username, subject, last in rows
    ], len(names) != len(set(names))
