"""Durable provider-scoped UUIDs, with race recovery and throttled activity writes."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from simple_module_db import independent_session
from sqlmodel import col
from starlette.requests import Request

logger = logging.getLogger(__name__)
_LAST_LOGIN_WRITE_INTERVAL = timedelta(minutes=5)


async def upsert_user_cache(
    request: Request,
    *,
    model: Any,
    identity: dict[str, str],
    email: str | None,
    name: str | None,
    update_name: bool = True,
    throttle_login: bool = False,
    session_factory: Any = independent_session,
) -> str | None:
    try:
        from sqlalchemy import or_, select, update
        from sqlalchemy.exc import IntegrityError

        now = datetime.now(UTC)
        async with session_factory(request.app) as db:
            stmt = select(model).where(
                *(getattr(model, key) == value for key, value in identity.items())
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
            if row is None:
                try:
                    async with db.begin_nested():
                        row = model(
                            **identity,
                            email=email if isinstance(email, str) else "",
                            full_name=name,
                            last_login_at=now,
                        )
                        db.add(row)
                        await db.flush()
                except IntegrityError:
                    # Another request inserted this sub after our SELECT.
                    row = (await db.execute(stmt)).scalar_one()

            if isinstance(email, str):
                row.email = email  # an absent or malformed claim keeps the last known address
            if update_name or row.full_name is None:
                row.full_name = name  # an absent claim keeps the last known name
            if not throttle_login:
                row.last_login_at = now
            else:
                cutoff = now - _LAST_LOGIN_WRITE_INTERVAL
                if row.last_login_at is None or row.last_login_at <= cutoff:
                    # Recheck in SQL so concurrent bearer requests share one touch.
                    await db.execute(
                        update(model)
                        .where(
                            col(model.id) == row.id,
                            or_(
                                col(model.last_login_at).is_(None),
                                col(model.last_login_at) <= cutoff,
                            ),
                        )
                        .values(last_login_at=now)
                    )
            return str(row.id)
    except Exception as exc:
        # Diagnosable without personal data: the error class and a short hash
        # of the identity, never the identity itself or a traceback whose SQL
        # parameters can carry the email.
        digest = hashlib.sha256(repr(sorted(identity.items())).encode()).hexdigest()[:12]
        logger.warning("Failed to persist OIDC identity %s (%s)", digest, type(exc).__name__)
        return None
