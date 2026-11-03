"""Durable issuer-scoped UUIDs, with race recovery and throttled activity writes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from simple_module_db import independent_session
from sqlmodel import col
from starlette.requests import Request

logger = logging.getLogger(__name__)
_LAST_LOGIN_WRITE_INTERVAL = timedelta(minutes=5)


class CachePersistence:
    async def _upsert_user_cache(
        self, request: Request, claims: dict, *, throttle_login: bool = False
    ) -> str | None:
        try:
            from sqlalchemy import or_, select, update
            from sqlalchemy.exc import IntegrityError

            from oidc.models import OidcUserCache

            issuer, subject = self._identity(claims)
            now = datetime.now(UTC)
            email = self._email(claims)
            async with independent_session(request.app) as db:
                stmt = select(OidcUserCache).where(
                    col(OidcUserCache.issuer) == issuer, col(OidcUserCache.subject) == subject
                )
                row = (await db.execute(stmt)).scalar_one_or_none()
                if row is None:
                    try:
                        async with db.begin_nested():
                            row = OidcUserCache(
                                issuer=issuer,
                                subject=subject,
                                email=email or "",
                                full_name=self._display_name(claims),
                                last_login_at=now,
                            )
                            db.add(row)
                            await db.flush()
                    except IntegrityError:
                        # Another request inserted this sub after our SELECT.
                        row = (await db.execute(stmt)).scalar_one()

                if email is not None:
                    row.email = email  # an absent claim keeps the last known address
                name = self._display_name(claims)
                if name or row.full_name is None:
                    row.full_name = name  # an absent claim keeps the last known name
                if not throttle_login:
                    row.last_login_at = now
                else:
                    cutoff = now - _LAST_LOGIN_WRITE_INTERVAL
                    if row.last_login_at is None or row.last_login_at <= cutoff:
                        # Recheck in SQL so concurrent bearer requests share one touch.
                        await db.execute(
                            update(OidcUserCache)
                            .where(
                                col(OidcUserCache.id) == row.id,
                                or_(
                                    col(OidcUserCache.last_login_at).is_(None),
                                    col(OidcUserCache.last_login_at) <= cutoff,
                                ),
                            )
                            .values(last_login_at=now)
                        )
                return str(row.id)
        except Exception:
            logger.warning("Failed to persist OIDC identity; refusing authentication")
            return None
